from datetime import date

import pydantic

from core.constants import PaymentProvider


class BookingQuoteInput(pydantic.BaseModel):
    listing_id: int
    start_date: date
    end_date: date


class BookingCheckoutInput(pydantic.BaseModel):
    quote_id: int
    provider: str
    pay_full_stay: bool = False

    @pydantic.field_validator("provider")
    @classmethod
    def validate_provider(cls, value):
        if value not in PaymentProvider.values():
            raise ValueError("Unsupported payment provider.")
        return value


class BookingDetailPath(pydantic.BaseModel):
    pk: int
