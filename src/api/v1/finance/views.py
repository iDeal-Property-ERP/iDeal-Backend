from datetime import date as date_type
from decimal import Decimal
from http import HTTPStatus

from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from dmr.pagination import Paginated
from finance.models import ExchangeRate, Payment, PayoutSchedule
from finance.utils import convert_amount

from api.v1.finance.schemas import (
    DashboardMetrics,
    ExchangeRateCreateInput,
    ExchangeRateOutput,
    PaymentCreateInput,
    PaymentOutput,
    PaymentPartialUpdateInput,
    PayoutScheduleOutput,
    PnLBreakdown,
    PnLFilter,
)
from core.api.views import (
    CreateAPIView,
    DetailPath,
    GenericController,
    ListAPIView,
    ListQuery,
)
from core.constants import Currency, PaymentStatus, PayoutStatus


class PaymentListCreateView(CreateAPIView, ListAPIView):
    model = Payment
    output_schema = PaymentOutput
    create_schema = PaymentCreateInput

    def get_queryset(self):
        return Payment.objects.select_related("lease", "tenant", "paid_by").all()

    def post(self, parsed_body: Body[PaymentCreateInput]) -> PaymentOutput:
        return super().post(parsed_body)

    def get(self, parsed_query: Query[ListQuery]) -> list[PaymentOutput] | Paginated[PaymentOutput]:
        return super().get(parsed_query)


class PaymentPartialUpdateView(GenericController):
    model = Payment
    output_schema = PaymentOutput

    def get_queryset(self):
        return Payment.objects.select_related("lease", "tenant", "paid_by").all()

    def patch(
        self, parsed_path: Path[DetailPath], parsed_body: Body[PaymentPartialUpdateInput]
    ) -> PaymentOutput:
        payment = self.get_object(pk=parsed_path.pk)
        data = parsed_body.model_dump(exclude_unset=True)
        for attr, value in data.items():
            setattr(payment, attr, value)
        payment.save()
        return self.ok(self.to_output(payment))


class PaymentMarkPaidView(GenericController):
    model = Payment
    output_schema = PaymentOutput

    def get_queryset(self):
        return Payment.objects.select_related("lease", "tenant", "paid_by").all()

    def post(self, parsed_path: Path[DetailPath]) -> PaymentOutput:
        payment = self.get_object(pk=parsed_path.pk)
        if payment.status == PaymentStatus.PAID:
            return self.fail(
                error=str(_("Payment is already marked as paid")),
                message=str(_("Invalid status transition")),
            )
        payment.status = PaymentStatus.PAID
        payment.payment_date = date_type.today()
        payment.save(update_fields=["status", "payment_date", "updated_at"])
        return self.ok(self.to_output(payment), status_code=HTTPStatus.OK)


class ExchangeRateListCreateView(CreateAPIView, ListAPIView):
    model = ExchangeRate
    output_schema = ExchangeRateOutput
    create_schema = ExchangeRateCreateInput

    def post(self, parsed_body: Body[ExchangeRateCreateInput]) -> ExchangeRateOutput:
        return super().post(parsed_body)

    def get(
        self, parsed_query: Query[ListQuery]
    ) -> list[ExchangeRateOutput] | Paginated[ExchangeRateOutput]:
        return super().get(parsed_query)


class PayoutScheduleListView(ListAPIView):
    model = PayoutSchedule
    output_schema = PayoutScheduleOutput

    def get_queryset(self):
        return PayoutSchedule.objects.select_related("owner_agreement", "owner").all()

    def get(
        self, parsed_query: Query[ListQuery]
    ) -> list[PayoutScheduleOutput] | Paginated[PayoutScheduleOutput]:
        return super().get(parsed_query)


def _safe_convert(amount, from_currency, to_currency):
    if float(amount) == 0:
        return Decimal("0.00")
    try:
        return convert_amount(amount, from_currency, to_currency)
    except ValueError:
        return Decimal("0.00")


class DashboardView(GenericController):
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
    def get(self, parsed_query: Query[PnLFilter]) -> PnLBreakdown:
        year = parsed_query.year
        month = parsed_query.month

        payment_qs = Payment.objects.filter(status=PaymentStatus.PAID)
        payout_qs = PayoutSchedule.objects.filter(status=PayoutStatus.PAID)

        if year:
            payment_qs = payment_qs.filter(payment_date__year=year)
            payout_qs = payout_qs.filter(paid_date__year=year)
        if month:
            payment_qs = payment_qs.filter(payment_date__month=month)
            payout_qs = payout_qs.filter(paid_date__month=month)

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
        )
        return self.ok(breakdown.model_dump(mode="json"))
