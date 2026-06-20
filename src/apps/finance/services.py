"""Transit financial system — auto-split company margin and accrue owner payout.

When a tenant :class:`~finance.models.Payment` becomes ``PAID``, the platform
keeps its management margin and accrues a :class:`~finance.models.PayoutSchedule`
to the owner for the guaranteed amount. The company margin is derived elsewhere
(``gross_revenue - owner_payouts`` in the dashboard / P&L views).
"""

import calendar
from datetime import date, datetime

from django.db import transaction
from finance.models import PayoutSchedule

from core.constants import PaymentStatus, PayoutStatus

# TODO: make the monthly payout day configurable per agreement / company.
PAYOUT_DAY = 25


def _as_date(value) -> date:
    """Coerce a date / datetime / ISO string into a ``date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _next_payout_date(from_date: date) -> date:
    """Return the next occurrence of ``PAYOUT_DAY`` on or after ``from_date``."""
    day = min(PAYOUT_DAY, calendar.monthrange(from_date.year, from_date.month)[1])
    candidate = from_date.replace(day=day)
    if candidate >= from_date:
        return candidate
    # Roll over to the next month.
    year = from_date.year + (1 if from_date.month == 12 else 0)
    month = 1 if from_date.month == 12 else from_date.month + 1
    day = min(PAYOUT_DAY, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def accrue_owner_payout_for_payment(payment):
    """Accrue an owner payout for a PAID ``payment``.

    Idempotent: the ``PayoutSchedule.source_payment`` OneToOne guarantees one
    payout per payment. Returns the created :class:`PayoutSchedule` or ``None``
    when nothing was accrued (not paid, no agreement, or already accrued).
    """
    if payment.status != PaymentStatus.PAID:
        return None

    if PayoutSchedule.objects.filter(source_payment=payment).exists():
        return None

    lease = payment.lease
    agreement = lease.owner_agreement
    if agreement is None:
        return None

    prop = agreement.property
    owner_amount = prop.owner_guaranteed_price
    owner_currency = prop.owner_guaranteed_currency

    with transaction.atomic():
        return PayoutSchedule.objects.create(
            owner_agreement=agreement,
            owner=agreement.owner,
            source_payment=payment,
            amount=owner_amount,
            currency=owner_currency,
            scheduled_date=_next_payout_date(_as_date(payment.payment_date)),
            status=PayoutStatus.SCHEDULED,
        )
