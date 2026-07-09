from datetime import date
from decimal import Decimal

from django.db.models import Q
from finance.models import ExchangeRate

from core.constants import PaymentStatus


def overdue_q(today: date) -> Q:
    """Predicate for payments that are effectively overdue.

    No background job flips ``PENDING`` payments to ``OVERDUE`` when their due
    date passes, so "overdue" must be derived: anything explicitly marked
    OVERDUE, plus any still-PENDING payment whose ``due_date`` is in the past.
    This is the single source of truth used by list filters, KPI stats, and the
    sidebar badge.
    """
    return Q(status=PaymentStatus.OVERDUE) | Q(status=PaymentStatus.PENDING, due_date__lt=today)


def convert_amount(amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
    if from_currency == to_currency:
        return amount

    if from_currency == "UZS":
        rate_obj = ExchangeRate.objects.filter(currency=to_currency).order_by("-effective_date", "-id").first()
        if rate_obj is None:
            raise ValueError(f"No exchange rate found for currency {to_currency}")
        return amount / rate_obj.rate

    if to_currency == "UZS":
        rate_obj = ExchangeRate.objects.filter(currency=from_currency).order_by("-effective_date", "-id").first()
        if rate_obj is None:
            raise ValueError(f"No exchange rate found for currency {from_currency}")
        return amount * rate_obj.rate

    rate_from = ExchangeRate.objects.filter(currency=from_currency).order_by("-effective_date", "-id").first()
    rate_to = ExchangeRate.objects.filter(currency=to_currency).order_by("-effective_date", "-id").first()
    if rate_from is None:
        raise ValueError(f"No exchange rate found for currency {from_currency}")
    if rate_to is None:
        raise ValueError(f"No exchange rate found for currency {to_currency}")

    amount_in_uzs = amount * rate_from.rate
    return amount_in_uzs / rate_to.rate
