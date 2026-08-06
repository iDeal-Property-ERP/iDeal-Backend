import logging
from datetime import date as date_type
from decimal import Decimal
from http import HTTPStatus

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from dmr.pagination import Paginated
from finance.models import ExchangeRate, OwnerSettlement, Payment, PayoutSchedule
from finance.utils import convert_amount
from notification.services import notify

from api.v1.finance.schemas import (
    DashboardMetrics,
    ExchangeRateCreateInput,
    ExchangeRateOutput,
    PaymentBulkActionOutput,
    PaymentBulkMarkPaidInput,
    PaymentCreateInput,
    PaymentOutput,
    PaymentPartialUpdateInput,
    PaymentRemindInput,
    PaymentRemindOutput,
    PayoutBulkActionOutput,
    PayoutBulkMarkPaidInput,
    PayoutScheduleCreateInput,
    PayoutScheduleOutput,
    PnLBreakdown,
    PnLFilter,
    SettlementAllocationOutput,
    SettlementOutput,
)
from core.api.permissions import RoleAuth
from core.api.views import (
    CreateAPIView,
    DetailPath,
    GenericController,
    ListAPIView,
    ListQuery,
    RetrieveAPIView,
)
from core.constants import (
    Currency,
    NotificationType,
    PaymentMethod,
    PaymentStatus,
    PayoutStatus,
    UserRole,
)

logger = logging.getLogger(__name__)


def _optional_json(request) -> dict:
    """Best-effort parse of a JSON request body; ``{}`` when absent or invalid.

    Lets detail-action endpoints (mark-paid / hold / cancel) accept an optional
    body without the framework rejecting a body-less request.
    """
    import json

    raw = getattr(request, "body", b"") or b""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _remind_body(payment) -> str:
    return str(_("Reminder: your payment of %(amount)s %(currency)s is due on %(due)s.")) % {
        "amount": payment.amount,
        "currency": payment.currency,
        "due": payment.due_date,
    }


class PaymentListCreateView(CreateAPIView, ListAPIView):
    model = Payment
    output_schema = PaymentOutput
    create_schema = PaymentCreateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return Payment.objects.select_related("lease", "tenant", "paid_by").all()

    def post(self, parsed_body: Body[PaymentCreateInput]) -> PaymentOutput:
        from contract.models import Lease

        from core.constants import PropertyEngagementType

        lease = Lease.objects.select_related("property").filter(pk=parsed_body.lease_id).first()
        if lease is None or lease.property.engagement_type != PropertyEngagementType.MANAGED:
            return self.fail(error=str(_("One-off brokerage properties cannot have rent payments")))
        # Bank transfers must carry a reference (mirrors the Record-payment dialog).
        if parsed_body.method == PaymentMethod.BANK_TRANSFER and not (parsed_body.gateway_ref or "").strip():
            return self.fail(
                error=str(_("A reference number is required for bank transfers")),
                message=str(_("Validation error")),
            )
        return super().post(parsed_body)

    def get(self, parsed_query: Query[ListQuery]) -> list[PaymentOutput] | Paginated[PaymentOutput]:
        return super().get(parsed_query)


class PaymentPartialUpdateView(GenericController):
    model = Payment
    output_schema = PaymentOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return Payment.objects.select_related("lease", "tenant", "paid_by").all()

    def get(self, parsed_path: Path[DetailPath]) -> PaymentOutput:
        payment = self.get_object(pk=parsed_path.pk)
        return self.ok(self.to_output(payment))

    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[PaymentPartialUpdateInput]) -> PaymentOutput:
        payment = self.get_object(pk=parsed_path.pk)
        data = parsed_body.model_dump(exclude_unset=True)
        if payment.status == PaymentStatus.PAID and set(data).intersection(
            {"amount", "currency", "payment_date", "due_date", "rental_period", "kind"}
        ):
            return self.fail(
                error=str(_("Paid rent receipts are immutable; record a reversal or adjustment instead")),
                message=str(_("Invalid financial correction")),
            )
        for attr, value in data.items():
            setattr(payment, attr, value)
        payment.save()
        return self.ok(self.to_output(payment))


class PaymentMarkPaidView(GenericController):
    model = Payment
    output_schema = PaymentOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return Payment.objects.select_related("lease", "tenant", "paid_by").all()

    def post(self, parsed_path: Path[DetailPath]) -> PaymentOutput:
        payment = self.get_object(pk=parsed_path.pk)
        if payment.status not in (PaymentStatus.PENDING, PaymentStatus.OVERDUE):
            return self.fail(
                error=str(_("Only pending or overdue payments can be marked as paid")),
                message=str(_("Invalid status transition")),
            )
        # Optional overrides (method / gateway_ref / payment_date) come from the
        # Mark-paid sheet. Parsed leniently so a body-less request still works.
        body = _optional_json(self.request)
        update_fields = ["status", "payment_date", "updated_at"]
        payment.status = PaymentStatus.PAID
        # Keep the recorded payment_date unless the mark-paid sheet overrides it;
        # only fall back to today when the payment has no date at all.
        payment.payment_date = body.get("payment_date") or payment.payment_date or date_type.today()
        if body.get("method"):
            payment.method = body["method"]
            update_fields.append("method")
        if body.get("gateway_ref") is not None:
            payment.gateway_ref = body["gateway_ref"]
            update_fields.append("gateway_ref")
        payment.save(update_fields=update_fields)
        notify(
            recipient=payment.tenant,
            type=NotificationType.PAYMENT_PAID,
            title=str(_("Payment received")),
            body=str(_("Your payment of %(amount)s %(currency)s has been recorded."))
            % {"amount": payment.amount, "currency": payment.currency},
            related_object_type="payment",
            related_object_id=payment.id,
        )
        return self.ok(self.to_output(payment), status_code=HTTPStatus.OK)


class PaymentBulkMarkPaidView(GenericController):
    model = Payment
    output_schema = PaymentOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def post(self, parsed_body: Body[PaymentBulkMarkPaidInput]) -> PaymentBulkActionOutput:
        payments = Payment.objects.select_related("tenant").filter(id__in=parsed_body.ids)
        updated = 0
        skipped = 0
        today = date_type.today()
        for payment in payments:
            if payment.status not in (PaymentStatus.PENDING, PaymentStatus.OVERDUE):
                skipped += 1
                continue
            payment.status = PaymentStatus.PAID
            payment.payment_date = today
            fields = ["status", "payment_date", "updated_at"]
            if parsed_body.method:
                payment.method = parsed_body.method
                fields.append("method")
            payment.save(update_fields=fields)  # post_save signal accrues the owner payout
            notify(
                recipient=payment.tenant,
                type=NotificationType.PAYMENT_PAID,
                title=str(_("Payment received")),
                body=str(_("Your payment of %(amount)s %(currency)s has been recorded."))
                % {"amount": payment.amount, "currency": payment.currency},
                related_object_type="payment",
                related_object_id=payment.id,
            )
            updated += 1
        # ids that matched no row are counted as skipped too.
        skipped += len(set(parsed_body.ids)) - payments.count()
        return self.ok({"updated": updated, "skipped": skipped}, status_code=HTTPStatus.OK)


class PaymentRemindView(GenericController):
    model = Payment
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def post(self, parsed_path: Path[DetailPath]) -> PaymentRemindOutput:
        payment = get_object_or_404(Payment.objects.select_related("tenant"), pk=parsed_path.pk)
        sent = _send_reminders([payment])
        return self.ok({"sent": sent}, status_code=HTTPStatus.OK)


class PaymentBulkRemindView(GenericController):
    model = Payment
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def post(self, parsed_body: Body[PaymentRemindInput]) -> PaymentRemindOutput:
        payments = Payment.objects.select_related("tenant").filter(id__in=parsed_body.ids)
        sent = _send_reminders(payments)
        return self.ok({"sent": sent}, status_code=HTTPStatus.OK)


def _send_reminders(payments) -> int:
    sent = 0
    for payment in payments:
        if payment.status not in (PaymentStatus.PENDING, PaymentStatus.OVERDUE):
            continue
        notify(
            recipient=payment.tenant,
            type=NotificationType.PAYMENT_DUE,
            title=str(_("Payment reminder")),
            body=_remind_body(payment),
            related_object_type="payment",
            related_object_id=payment.id,
        )
        sent += 1
    return sent


class ExchangeRateListCreateView(CreateAPIView, ListAPIView):
    model = ExchangeRate
    output_schema = ExchangeRateOutput
    create_schema = ExchangeRateCreateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def post(self, parsed_body: Body[ExchangeRateCreateInput]) -> ExchangeRateOutput:
        # Upsert on (currency, effective_date) so a given currency has exactly one
        # rate per day — prevents ambiguous duplicates that make conversion
        # nondeterministic. (A hard DB unique constraint is avoided because legacy
        # seed data already contains same-day duplicates.)
        rate, _created = ExchangeRate.objects.update_or_create(
            currency=parsed_body.currency,
            effective_date=parsed_body.effective_date,
            defaults={"rate": parsed_body.rate},
        )
        status_code = HTTPStatus.CREATED if _created else HTTPStatus.OK
        return self.ok(self.to_output(rate), status_code=status_code)

    def get(self, parsed_query: Query[ListQuery]) -> list[ExchangeRateOutput] | Paginated[ExchangeRateOutput]:
        return super().get(parsed_query)


class PayoutScheduleListCreateView(CreateAPIView, ListAPIView):
    model = PayoutSchedule
    output_schema = PayoutScheduleOutput
    create_schema = PayoutScheduleCreateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return PayoutSchedule.objects.select_related("owner_agreement", "owner").all()

    def get(self, parsed_query: Query[ListQuery]) -> list[PayoutScheduleOutput] | Paginated[PayoutScheduleOutput]:
        return super().get(parsed_query)

    def post(self, parsed_body: Body[PayoutScheduleCreateInput]) -> PayoutScheduleOutput:
        from contract.models import OwnerAgreement

        from core.constants import PropertyEngagementType

        agreement = get_object_or_404(OwnerAgreement, pk=parsed_body.owner_agreement_id)
        if agreement.property.engagement_type != PropertyEngagementType.MANAGED:
            return self.fail(error=str(_("One-off brokerage properties cannot have owner payouts")))
        payout = PayoutSchedule.objects.create(
            owner_agreement=agreement,
            owner=agreement.owner,
            amount=parsed_body.amount,
            currency=parsed_body.currency,
            scheduled_date=parsed_body.scheduled_date,
            method=parsed_body.method,
            status=PayoutStatus.SCHEDULED,
        )
        return self.ok(self.to_output(payout), status_code=HTTPStatus.CREATED)


class SettlementListView(ListAPIView):
    """Management ledger view; owners use the scoped equivalent below."""

    model = OwnerSettlement
    output_schema = SettlementOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        qs = OwnerSettlement.objects.select_related("owner_agreement__property", "owner").prefetch_related(
            "receipt_allocations"
        )
        if owner_id := self.request.GET.get("owner_id"):
            qs = qs.filter(owner_id=owner_id)
        if agreement_id := self.request.GET.get("owner_agreement_id"):
            qs = qs.filter(owner_agreement_id=agreement_id)
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> list[SettlementOutput] | Paginated[SettlementOutput]:
        return super().get(parsed_query)


class SettlementDetailView(RetrieveAPIView):
    model = OwnerSettlement
    output_schema = SettlementOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return OwnerSettlement.objects.select_related("owner_agreement__property", "owner").prefetch_related(
            "receipt_allocations"
        )


class SettlementAllocationsView(GenericController):
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get(self, parsed_path: Path[DetailPath]) -> list[SettlementAllocationOutput]:
        settlement = get_object_or_404(OwnerSettlement, pk=parsed_path.pk)
        return self.ok(
            [SettlementAllocationOutput.model_validate(row).model_dump(mode="json") for row in settlement.receipt_allocations.all()]
        )


class PayoutScheduleBulkMarkPaidView(GenericController):
    model = PayoutSchedule
    output_schema = PayoutScheduleOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def post(self, parsed_body: Body[PayoutBulkMarkPaidInput]) -> PayoutBulkActionOutput:
        payouts = PayoutSchedule.objects.select_related("owner").filter(id__in=parsed_body.ids)
        updated = 0
        skipped = 0
        today = date_type.today()
        for payout in payouts:
            if payout.status not in (PayoutStatus.SCHEDULED, PayoutStatus.HELD):
                skipped += 1
                continue
            payout.status = PayoutStatus.PAID
            payout.paid_date = today
            payout.save(update_fields=["status", "paid_date", "updated_at"])
            notify(
                recipient=payout.owner,
                type=NotificationType.PAYOUT_PAID,
                title=str(_("Payout sent")),
                body=str(_("Your payout of %(amount)s %(currency)s has been paid."))
                % {"amount": payout.amount, "currency": payout.currency},
                related_object_type="payout",
                related_object_id=payout.id,
            )
            updated += 1
        skipped += len(set(parsed_body.ids)) - payouts.count()
        return self.ok({"updated": updated, "skipped": skipped}, status_code=HTTPStatus.OK)


class PayoutScheduleHoldView(GenericController):
    model = PayoutSchedule
    output_schema = PayoutScheduleOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return PayoutSchedule.objects.select_related("owner_agreement", "owner").all()

    def post(self, parsed_path: Path[DetailPath]) -> PayoutScheduleOutput:
        payout = self.get_object(pk=parsed_path.pk)
        if payout.status != PayoutStatus.SCHEDULED:
            return self.fail(
                error=str(_("Only scheduled payouts can be held")),
                message=str(_("Invalid status transition")),
            )
        reason = (_optional_json(self.request).get("reason") or "").strip()
        if not reason:
            return self.fail(
                error=str(_("A reason is required to hold a payout")),
                message=str(_("Validation error")),
            )
        payout.status = PayoutStatus.HELD
        payout.status_reason = reason
        payout.save(update_fields=["status", "status_reason", "updated_at"])
        return self.ok(self.to_output(payout), status_code=HTTPStatus.OK)


class PayoutScheduleReleaseView(GenericController):
    model = PayoutSchedule
    output_schema = PayoutScheduleOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return PayoutSchedule.objects.select_related("owner_agreement", "owner").all()

    def post(self, parsed_path: Path[DetailPath]) -> PayoutScheduleOutput:
        payout = self.get_object(pk=parsed_path.pk)
        if payout.status != PayoutStatus.HELD:
            return self.fail(
                error=str(_("Only held payouts can be released")),
                message=str(_("Invalid status transition")),
            )
        payout.status = PayoutStatus.SCHEDULED
        payout.status_reason = None
        payout.save(update_fields=["status", "status_reason", "updated_at"])
        return self.ok(self.to_output(payout), status_code=HTTPStatus.OK)


class PayoutScheduleDetailView(RetrieveAPIView):
    model = PayoutSchedule
    output_schema = PayoutScheduleOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return PayoutSchedule.objects.select_related("owner_agreement", "owner").all()

    def get(self, parsed_path: Path[DetailPath]) -> PayoutScheduleOutput:
        return super().get(parsed_path)


class PayoutScheduleMarkPaidView(GenericController):
    model = PayoutSchedule
    output_schema = PayoutScheduleOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return PayoutSchedule.objects.select_related("owner_agreement", "owner").all()

    def post(self, parsed_path: Path[DetailPath]) -> PayoutScheduleOutput:
        payout = self.get_object(pk=parsed_path.pk)
        if payout.status == PayoutStatus.PAID:
            return self.fail(
                error=str(_("Payout is already marked as paid")),
                message=str(_("Invalid status transition")),
            )
        payout.status = PayoutStatus.PAID
        payout.paid_date = date_type.today()
        payout.save(update_fields=["status", "paid_date", "updated_at"])
        notify(
            recipient=payout.owner,
            type=NotificationType.PAYOUT_PAID,
            title=str(_("Payout sent")),
            body=str(_("Your payout of %(amount)s %(currency)s has been paid."))
            % {"amount": payout.amount, "currency": payout.currency},
            related_object_type="payout",
            related_object_id=payout.id,
        )
        return self.ok(self.to_output(payout), status_code=HTTPStatus.OK)


class PayoutScheduleCancelView(GenericController):
    model = PayoutSchedule
    output_schema = PayoutScheduleOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return PayoutSchedule.objects.select_related("owner_agreement", "owner").all()

    def post(self, parsed_path: Path[DetailPath]) -> PayoutScheduleOutput:
        payout = self.get_object(pk=parsed_path.pk)
        if payout.status == PayoutStatus.PAID:
            return self.fail(
                error=str(_("Cannot cancel a payout that has already been paid")),
                message=str(_("Invalid status transition")),
            )
        reason = _optional_json(self.request).get("reason")
        payout.status = PayoutStatus.CANCELLED
        fields = ["status", "updated_at"]
        if reason is not None:
            payout.status_reason = reason
            fields.append("status_reason")
        payout.save(update_fields=fields)
        return self.ok(self.to_output(payout), status_code=HTTPStatus.OK)


def _safe_convert(amount, from_currency, to_currency):
    if float(amount) == 0:
        return Decimal("0.00")
    try:
        return convert_amount(amount, from_currency, to_currency)
    except ValueError:
        # A non-zero amount could not be converted (missing exchange rate). Do not
        # silently corrupt aggregated totals — surface it in the logs so it is
        # investigable. Currencies are validated at write-time, so this indicates a
        # genuinely missing rate for a supported currency.
        logger.warning(
            "Currency conversion failed: %s %s -> %s (missing rate); excluded from total.",
            amount,
            from_currency,
            to_currency,
        )
        return Decimal("0.00")


class DashboardView(GenericController):
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get(self) -> DashboardMetrics:
        paid_payments = Payment.objects.filter(status=PaymentStatus.PAID)
        total_payments = paid_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        total_payments_uzs = Decimal("0.00")
        for p in paid_payments:
            total_payments_uzs += _safe_convert(p.amount, p.currency, Currency.UZS)

        paid_payouts = PayoutSchedule.objects.filter(status=PayoutStatus.PAID)
        total_payouts = paid_payouts.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        total_payouts_uzs = Decimal("0.00")
        for p in paid_payouts:
            total_payouts_uzs += _safe_convert(p.amount, p.currency, Currency.UZS)

        net_margin = total_payments_uzs - total_payouts_uzs
        net_margin_usd = _safe_convert(net_margin, Currency.UZS, Currency.USD)

        pending_qs = Payment.objects.filter(status=PaymentStatus.PENDING)
        pending_count = pending_qs.count()
        pending_amount = pending_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        overdue_qs = Payment.objects.filter(status=PaymentStatus.OVERDUE)
        overdue_count = overdue_qs.count()
        overdue_amount = overdue_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        metrics = DashboardMetrics(
            total_payments=total_payments,
            total_payments_uzs=total_payments_uzs,
            total_payouts=total_payouts,
            total_payouts_uzs=total_payouts_uzs,
            net_margin=net_margin_usd,
            net_margin_uzs=net_margin,
            pending_count=pending_count,
            pending_amount=pending_amount,
            overdue_count=overdue_count,
            overdue_amount=overdue_amount,
        )
        return self.ok(metrics.model_dump(mode="json"))


class PnLView(GenericController):
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get(self, parsed_query: Query[PnLFilter]) -> PnLBreakdown:
        from finance.models import OwnerSettlement

        year = parsed_query.year
        month = parsed_query.month
        start_date = parsed_query.start_date
        end_date = parsed_query.end_date

        payment_qs = Payment.objects.filter(status=PaymentStatus.PAID)
        payout_qs = PayoutSchedule.objects.filter(status=PayoutStatus.PAID)

        if year:
            payment_qs = payment_qs.filter(payment_date__year=year)
            payout_qs = payout_qs.filter(paid_date__year=year)
        if month:
            payment_qs = payment_qs.filter(payment_date__month=month)
            payout_qs = payout_qs.filter(paid_date__month=month)
        if start_date:
            payment_qs = payment_qs.filter(payment_date__gte=start_date)
            payout_qs = payout_qs.filter(paid_date__gte=start_date)
        if end_date:
            payment_qs = payment_qs.filter(payment_date__lte=end_date)
            payout_qs = payout_qs.filter(paid_date__lte=end_date)

        gross_revenue_uzs = Decimal("0.00")
        for p in payment_qs:
            gross_revenue_uzs += _safe_convert(p.amount, p.currency, Currency.UZS)

        owner_payouts_uzs = Decimal("0.00")
        for p in payout_qs:
            owner_payouts_uzs += _safe_convert(p.amount, p.currency, Currency.UZS)

        net_margin_uzs = gross_revenue_uzs - owner_payouts_uzs
        tax_estimate_uzs = net_margin_uzs * Decimal("0.12")

        net_margin_usd = _safe_convert(net_margin_uzs, Currency.UZS, Currency.USD)
        gross_revenue_usd = _safe_convert(gross_revenue_uzs, Currency.UZS, Currency.USD)
        owner_payouts_usd = _safe_convert(owner_payouts_uzs, Currency.UZS, Currency.USD)
        tax_estimate_usd = _safe_convert(tax_estimate_uzs, Currency.UZS, Currency.USD)

        payment_count = payment_qs.count()
        settlement_qs = OwnerSettlement.objects.all()
        if year:
            settlement_qs = settlement_qs.filter(period_start__year=year)
        if month:
            settlement_qs = settlement_qs.filter(period_start__month=month)
        if start_date:
            settlement_qs = settlement_qs.filter(period_start__gte=start_date)
        if end_date:
            settlement_qs = settlement_qs.filter(period_start__lte=end_date)
        contractual_commission = Decimal("0.00")
        ideal_cash_exposure = Decimal("0.00")
        for settlement in settlement_qs:
            contractual_commission += _safe_convert(settlement.commission_amount, settlement.currency, Currency.USD)
            ideal_cash_exposure += _safe_convert(settlement.ideal_cash_exposure, settlement.currency, Currency.USD)
        cash_collected = sum(
            (_safe_convert(payment.amount, payment.currency, Currency.USD) for payment in payment_qs), Decimal("0.00")
        )

        breakdown = PnLBreakdown(
            gross_revenue=gross_revenue_usd,
            gross_revenue_uzs=gross_revenue_uzs,
            owner_payouts=owner_payouts_usd,
            owner_payouts_uzs=owner_payouts_uzs,
            net_margin=net_margin_usd,
            net_margin_uzs=net_margin_uzs,
            payment_count=payment_count,
            tax_estimate=tax_estimate_usd,
            tax_estimate_uzs=tax_estimate_uzs,
            cash_collected=cash_collected,
            contractual_commission=contractual_commission,
            ideal_cash_exposure=ideal_cash_exposure,
            net_cash_position=cash_collected - owner_payouts_usd,
        )
        return self.ok(breakdown.model_dump(mode="json"))
