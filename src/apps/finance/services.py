"""Transparent agreement-month settlement ledger."""

import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum
from finance.models import OwnerSettlement, PayoutSchedule, RentReceiptAllocation

from core.constants import PaymentKind, PaymentStatus, PayoutKind, PayoutStatus

MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _month_bounds(value: date) -> tuple[date, date]:
    start = value.replace(day=1)
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])


def _payout_date(period_start: date, payout_day: int) -> date:
    return period_start.replace(day=min(payout_day, calendar.monthrange(period_start.year, period_start.month)[1]))


def _next_payout_date(from_date: date, payout_day: int) -> date:
    candidate = _payout_date(from_date, payout_day)
    if candidate >= from_date:
        return candidate
    next_month = (from_date.replace(day=28) + timedelta(days=4)).replace(day=1)
    return _payout_date(next_month, payout_day)


def next_payout_run_date(from_date: date | None = None) -> date:
    """Compatibility helper for operational dashboards."""
    return _next_payout_date(from_date or date.today(), payout_day=25)


def _calculation(settlement: OwnerSettlement) -> dict[str, Decimal]:
    floor = _money(settlement.gross_floor_amount * settlement.covered_days / settlement.days_in_month)
    received = _money(settlement.receipt_allocations.aggregate(total=Sum("amount"))["total"] or Decimal("0"))
    base = max(floor, received)
    commission = _money(base * settlement.commission_rate / Decimal("100"))
    owner_payout = _money(base - commission)
    return {
        "rent_received_amount": received,
        "settlement_base_amount": base,
        "commission_amount": commission,
        "owner_payout_amount": owner_payout,
        "ideal_cash_exposure": max(_money(owner_payout - received), Decimal("0.00")),
    }


@transaction.atomic
def recalculate_settlement(settlement: OwnerSettlement, adjustment_from_date: date | None = None) -> OwnerSettlement:
    """Refresh a settlement and create late-rent upside adjustments when needed."""
    settlement = OwnerSettlement.objects.select_for_update().get(pk=settlement.pk)
    old_owner_payout = settlement.owner_payout_amount
    values = _calculation(settlement)
    for field, value in values.items():
        setattr(settlement, field, value)
    settlement.save(update_fields=[*values.keys(), "updated_at"])
    base = settlement.payouts.filter(kind=PayoutKind.BASE).first()
    if base is None:
        PayoutSchedule.objects.create(
            owner_agreement=settlement.owner_agreement,
            owner=settlement.owner,
            settlement=settlement,
            kind=PayoutKind.BASE,
            amount=settlement.owner_payout_amount,
            currency=settlement.currency,
            scheduled_date=_payout_date(settlement.period_start, settlement.owner_agreement.payout_day),
        )
    elif base.status in (PayoutStatus.SCHEDULED, PayoutStatus.HELD):
        base.amount = settlement.owner_payout_amount
        base.save(update_fields=["amount", "updated_at"])
    elif settlement.owner_payout_amount > old_owner_payout:
        PayoutSchedule.objects.create(
            owner_agreement=settlement.owner_agreement,
            owner=settlement.owner,
            settlement=settlement,
            kind=PayoutKind.UPSIDE_ADJUSTMENT,
            amount=_money(settlement.owner_payout_amount - old_owner_payout),
            currency=settlement.currency,
            scheduled_date=_next_payout_date(
                adjustment_from_date or date.today(), settlement.owner_agreement.payout_day
            ),
        )
    return settlement


@transaction.atomic
def ensure_monthly_settlements(through: date | None = None) -> int:
    """Idempotently create a settlement and guaranteed base payout per active month."""
    from contract.models import OwnerAgreement

    through = through or date.today()
    created = 0
    for agreement in OwnerAgreement.objects.select_for_update().filter(start_date__lte=through):
        last = min(agreement.end_date, through)
        if agreement.start_date > last:
            continue
        cursor = agreement.start_date.replace(day=1)
        while cursor <= last:
            month_start, month_end = _month_bounds(cursor)
            covered_start, covered_end = max(month_start, agreement.start_date), min(month_end, agreement.end_date)
            if covered_start > covered_end:
                cursor = (month_end + timedelta(days=1)).replace(day=1)
                continue
            settlement, was_created = OwnerSettlement.objects.get_or_create(
                owner_agreement=agreement,
                period_start=month_start,
                defaults={
                    "owner": agreement.owner,
                    "period_end": month_end,
                    "covered_days": (covered_end - covered_start).days + 1,
                    "days_in_month": calendar.monthrange(month_start.year, month_start.month)[1],
                    "gross_floor_amount": agreement.gross_floor_amount,
                    "commission_rate": agreement.commission_rate,
                    "currency": agreement.currency,
                },
            )
            recalculate_settlement(settlement)
            created += int(was_created)
            cursor = (month_end + timedelta(days=1)).replace(day=1)
    return created


@transaction.atomic
def allocate_paid_rent(payment) -> OwnerSettlement | None:
    """Allocate a paid rent receipt to its rental month; deposits are excluded."""
    if payment.status != PaymentStatus.PAID or payment.kind != PaymentKind.RENT:
        return None
    coverage = list(payment.coverage_allocations.select_related("owner_agreement").order_by("start_date"))
    if coverage:
        last_settlement = None
        for item in coverage:
            period_start, _ = _month_bounds(item.start_date)
            ensure_monthly_settlements(period_start)
            settlement = OwnerSettlement.objects.filter(
                owner_agreement=item.owner_agreement, period_start=period_start
            ).first()
            if settlement is None:
                continue
            if payment.currency != settlement.currency:
                raise ValueError("Rent payment currency must match its settlement currency.")
            allocation, created = RentReceiptAllocation.objects.get_or_create(
                payment=payment, settlement=settlement, defaults={"amount": item.amount}
            )
            if not created:
                expected = sum(
                    (row.amount for row in coverage if row.owner_agreement_id == item.owner_agreement_id and row.start_date.replace(day=1) == period_start),
                    Decimal("0"),
                )
                if allocation.amount != expected:
                    allocation.amount = expected
                    allocation.save(update_fields=["amount", "updated_at"])
            last_settlement = recalculate_settlement(settlement, adjustment_from_date=payment.payment_date)
        return last_settlement
    period_start, _ = _month_bounds(payment.rental_period or payment.due_date)
    ensure_monthly_settlements(period_start)
    settlement = OwnerSettlement.objects.filter(
        owner_agreement=payment.lease.owner_agreement, period_start=period_start
    ).first()
    if settlement is None:
        return None
    if payment.currency != settlement.currency:
        raise ValueError("Rent payment currency must match its settlement currency.")
    allocated = payment.settlement_allocations.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    remaining = _money(Decimal(str(payment.amount)) - allocated)
    if remaining > 0:
        RentReceiptAllocation.objects.create(payment=payment, settlement=settlement, amount=remaining)
    return recalculate_settlement(settlement, adjustment_from_date=payment.payment_date)
