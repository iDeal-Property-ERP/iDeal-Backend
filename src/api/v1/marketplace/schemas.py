from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic
from property.services.validation import validate_and_normalize_landmark, validate_floor_bounds
from pydantic import field_validator

from core.utils.html_sanitizer import sanitize_description_html


class AmenityBrief(pydantic.BaseModel):
    slug: str
    name: str
    icon: str = ""

    model_config = pydantic.ConfigDict(from_attributes=True)


class PropertyBrief(pydantic.BaseModel):
    id: int
    name: str
    address: str
    landmark: str | None = None
    district_id: int
    district_name: str | None = None
    property_type: str
    engagement_type: str = "managed"
    rooms: int
    area_sqm: int
    floor: int
    total_floors: int | None
    furnishing: str
    status: str
    is_verified: bool
    score: Decimal
    map_lat: Decimal | None
    map_lon: Decimal | None
    tariff: str
    ask_price: Decimal
    ask_currency: str
    amenities: list[AmenityBrief] = []
    image_url: str | None = None
    image_urls: list[str] = []

    model_config = pydantic.ConfigDict(from_attributes=True)


class ListingOutput(pydantic.BaseModel):
    id: int
    property: PropertyBrief | None = None
    property_id: int
    owner_agreement_id: int | None
    status: str
    is_active: bool
    is_featured: bool
    description: str | None
    listed_price: Decimal | None
    monthly_price: Decimal | None
    deposit_amount: Decimal | None
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class DistrictOutput(pydantic.BaseModel):
    id: int
    name: str
    city: str

    model_config = pydantic.ConfigDict(from_attributes=True)


class FaqOutput(pydantic.BaseModel):
    id: int
    question: str
    answer: str
    sort_order: int

    model_config = pydantic.ConfigDict(from_attributes=True)


class ListingMapOutput(pydantic.BaseModel):
    type: str = "FeatureCollection"
    features: list[dict]


class ViewingRequestCreateInput(pydantic.BaseModel):
    full_name: str
    phone: str
    email: str | None = None
    preferred_date: date
    preferred_time: str | None = None
    message: str | None = None


class ViewingRequestOutput(pydantic.BaseModel):
    id: int
    listing_id: int
    full_name: str
    phone: str
    email: str | None
    preferred_date: date
    preferred_time: str | None
    message: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class ContactInquiryCreateInput(pydantic.BaseModel):
    listing_id: int | None = None
    full_name: str = pydantic.Field(min_length=1, max_length=150)
    phone: str
    email: str | None = None
    message: str = pydantic.Field(min_length=1, max_length=2000)

    model_config = pydantic.ConfigDict(str_strip_whitespace=True)

    @pydantic.field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        from core.utils.phone import normalize_uzbekistan_phone

        return normalize_uzbekistan_phone(value)


class ContactInquiryOutput(pydantic.BaseModel):
    id: int
    listing_id: int | None
    full_name: str
    phone: str
    email: str | None
    message: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class PublicListingContactInput(pydantic.BaseModel):
    first_name: str
    last_name: str | None = None
    email: str
    phone: str


class PublicListingSubmitInput(pydantic.BaseModel):
    # Contact
    contact: PublicListingContactInput

    # Details
    property_type: str
    engagement_type: str = "managed"
    name: str
    landmark: str | None = None
    district_id: int
    rooms: int = pydantic.Field(ge=1)
    area_sqm: int = pydantic.Field(ge=0)
    floor: int = pydantic.Field(default=0, ge=0)
    total_floors: int | None = pydantic.Field(default=None, ge=0)
    furnishing: str
    description: str | None = None
    amenities: list[str] = pydantic.Field(default_factory=list)

    # Pricing
    monthly_price: Decimal = pydantic.Field(ge=0)
    deposit_amount: Decimal = pydantic.Field(ge=0)
    currency: str = "USD"
    minimum_stay: int = pydantic.Field(default=6, ge=0)
    price_includes: list[str] = pydantic.Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: str | None) -> str | None:
        return sanitize_description_html(v)

    @field_validator("landmark")
    @classmethod
    def normalize_landmark(cls, v: str | None) -> str | None:
        return validate_and_normalize_landmark(v)

    @pydantic.model_validator(mode="after")
    def validate_floor_bounds(self):
        validate_floor_bounds(self.floor, self.total_floors)
        return self
