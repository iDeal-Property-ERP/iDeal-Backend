from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

import pydantic
from property.services.validation import validate_and_normalize_landmark, validate_floor_bounds
from pydantic import field_validator


class OwnerPropertyOutput(pydantic.BaseModel):
    id: int
    name: str
    address: str
    landmark: str | None = None
    rooms: int
    area_sqm: int
    floor: int
    total_floors: int | None
    status: str
    tariff: str
    ask_price: Decimal
    ask_currency: str
    vacant_since: date | None
    vacant_days: int
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class OwnerEarningsOutput(pydantic.BaseModel):
    total_guaranteed: Decimal
    total_paid: Decimal
    total_pending: Decimal
    total_above_guarantee: Decimal
    next_payout_amount: Decimal
    currency: str


class OwnerSettlementOutput(pydantic.BaseModel):
    id: int
    property_name: str
    period_start: date
    period_end: date
    gross_floor_amount: Decimal
    commission_rate: Decimal
    currency: str
    rent_received_amount: Decimal
    settlement_base_amount: Decimal
    commission_amount: Decimal
    owner_payout_amount: Decimal
    ideal_cash_exposure: Decimal
    payout_status: str | None
    payout_amount: Decimal | None
    payout_kind: str | None


class OwnerWhyOutput(pydantic.BaseModel):
    title: str
    description: str
    benefits: list[str]


class PublicOfferOutput(pydantic.BaseModel):
    id: int
    version: str
    body: str

    model_config = pydantic.ConfigDict(from_attributes=True)


class OwnerOnboardingCreateInput(pydantic.BaseModel):
    name: str
    address: str
    landmark: str | None = None
    district_id: int
    rooms: int = pydantic.Field(gt=0)
    area_sqm: int = pydantic.Field(gt=0)
    floor: int = pydantic.Field(ge=0)
    total_floors: int | None = pydantic.Field(default=None, ge=0)
    description: str | None = None
    ask_price: Decimal
    ask_currency: str = "USD"
    content_locale: Literal["en", "uz", "ru"] | None = None
    accept_offer: Literal[True]

    @field_validator("landmark")
    @classmethod
    def normalize_landmark(cls, v: str | None) -> str | None:
        return validate_and_normalize_landmark(v)

    @pydantic.model_validator(mode="after")
    def validate_floor_bounds(self):
        validate_floor_bounds(self.floor, self.total_floors)
        return self


class OwnerContactInput(pydantic.BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None


class OwnerListingSubmitPayload(pydantic.BaseModel):
    property_type: str = "apartment"
    name: str | None = None
    address: str | None = None
    landmark: str | None = None
    district_id: int
    rooms: int = pydantic.Field(gt=0)
    area_sqm: int = pydantic.Field(gt=0)
    floor: int = pydantic.Field(default=1, ge=0)
    total_floors: int | None = pydantic.Field(default=None, ge=0)
    furnishing: str = "unfurnished"
    description: str | None = None
    tariff: str = "standard"
    monthly_price: Decimal = pydantic.Field(ge=0)
    deposit_amount: Decimal = Decimal("0.00")
    currency: str = "USD"
    minimum_stay: int = 6
    price_includes: list[str] = pydantic.Field(default_factory=list)
    amenities: list[str] = pydantic.Field(default_factory=list)
    captions: list[str] = pydantic.Field(default_factory=list)
    content_locale: Literal["en", "uz", "ru"] | None = None
    contact: OwnerContactInput | None = None
    accept_offer: Literal[True]

    @field_validator("landmark")
    @classmethod
    def normalize_landmark(cls, v: str | None) -> str | None:
        return validate_and_normalize_landmark(v)

    @pydantic.model_validator(mode="after")
    def validate_floor_bounds(self):
        validate_floor_bounds(self.floor, self.total_floors)
        return self


class OwnerListingResubmitPayload(OwnerListingSubmitPayload):
    keep_photo_ids: list[int] = pydantic.Field(default_factory=list)


class OwnerOnboardingOutput(pydantic.BaseModel):
    id: int
    owner_id: int
    property_id: int
    property_name: str
    status: str
    offer_version: str | None
    offer_accepted_at: datetime | None
    review_notes: str | None
    generated_agreement_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)

    @pydantic.model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "owner_id": v.owner_id,
            "property_id": v.property_id,
            "property_name": v.property.name,
            "status": v.status,
            "offer_version": v.offer_version,
            "offer_accepted_at": v.offer_accepted_at,
            "review_notes": v.review_notes,
            "generated_agreement_id": v.generated_agreement_id,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }
