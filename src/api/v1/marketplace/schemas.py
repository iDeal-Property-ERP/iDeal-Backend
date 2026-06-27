from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic


class AmenityBrief(pydantic.BaseModel):
    slug: str
    name: str
    icon: str = ""

    model_config = pydantic.ConfigDict(from_attributes=True)


class PropertyBrief(pydantic.BaseModel):
    id: int
    name: str
    address: str
    district_id: int
    district_name: str | None = None
    property_type: str
    rooms: int
    bathrooms: int
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
    full_name: str
    phone: str
    email: str | None = None
    message: str


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
