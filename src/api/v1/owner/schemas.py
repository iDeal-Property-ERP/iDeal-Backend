from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic


class OwnerPropertyOutput(pydantic.BaseModel):
    id: int
    name: str
    address: str
    rooms: int
    area_sqm: int
    floor: int
    total_floors: int | None
    status: str
    tariff: str
    ask_price: Decimal
    ask_currency: str
    owner_guaranteed_price: Decimal
    owner_guaranteed_currency: str
    tenant_charge_price: Decimal
    tenant_charge_currency: str
    vacant_since: date | None
    vacant_days: int
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class OwnerEarningsOutput(pydantic.BaseModel):
    total_guaranteed: Decimal
    total_paid: Decimal
    total_pending: Decimal
    currency: str


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
    district_id: int
    rooms: int
    area_sqm: int
    floor: int
    total_floors: int | None = None
    description: str | None = None
    ask_price: Decimal
    ask_currency: str = "USD"
    accept_offer: bool


class OwnerListingCreateInput(pydantic.BaseModel):
    """Step 1 (Details) of the List-Your-Property wizard. Creates a draft."""

    property_type: str = "apartment"
    name: str
    address: str | None = None
    district_id: int
    rooms: int
    area_sqm: int
    floor: int = 1
    total_floors: int | None = None
    furnishing: str = "unfurnished"
    description: str | None = None
    amenities: list[str] = []  # amenity slugs


class OwnerListingUpdateInput(pydantic.BaseModel):
    """Partial per-step update. Pricing fields land on the listing; the rest on the property."""

    property_type: str | None = None
    name: str | None = None
    address: str | None = None
    district_id: int | None = None
    rooms: int | None = None
    area_sqm: int | None = None
    floor: int | None = None
    total_floors: int | None = None
    furnishing: str | None = None
    tariff: str | None = None
    description: str | None = None
    amenities: list[str] | None = None
    monthly_price: Decimal | None = None
    deposit_amount: Decimal | None = None
    currency: str | None = None
    minimum_stay: int | None = None
    price_includes: list[str] | None = None


class OwnerListingPhotoReorderItem(pydantic.BaseModel):
    id: int
    sort_order: int = 0
    is_primary: bool = False
    caption: str | None = None


class OwnerListingPhotoReorderInput(pydantic.BaseModel):
    items: list[OwnerListingPhotoReorderItem]


class OwnerListingSubmitInput(pydantic.BaseModel):
    accept_offer: bool


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
