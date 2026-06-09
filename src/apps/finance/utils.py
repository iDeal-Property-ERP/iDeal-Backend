from decimal import Decimal

from finance.models import ExchangeRate


def convert_amount(amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
    if from_currency == to_currency:
        return amount

    if from_currency == "UZS":
        rate_obj = ExchangeRate.objects.filter(currency=to_currency).order_by("-effective_date").first()
        if rate_obj is None:
            raise ValueError(f"No exchange rate found for currency {to_currency}")
        return amount / rate_obj.rate

    if to_currency == "UZS":
        rate_obj = ExchangeRate.objects.filter(currency=from_currency).order_by("-effective_date").first()
        if rate_obj is None:
            raise ValueError(f"No exchange rate found for currency {from_currency}")
        return amount * rate_obj.rate

    rate_from = ExchangeRate.objects.filter(currency=from_currency).order_by("-effective_date").first()
    rate_to = ExchangeRate.objects.filter(currency=to_currency).order_by("-effective_date").first()
    if rate_from is None:
        raise ValueError(f"No exchange rate found for currency {from_currency}")
    if rate_to is None:
        raise ValueError(f"No exchange rate found for currency {to_currency}")

    amount_in_uzs = amount * rate_from.rate
    return amount_in_uzs / rate_to.rate
