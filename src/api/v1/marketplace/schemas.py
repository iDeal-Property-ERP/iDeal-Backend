from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic


class PropertyBrief(pydantic.BaseModel):
    id: int
    name: str
    address: str
    district_id: int
    district_name: str | None = None
    rooms: int
    area_sqm: int
    floor: int
    total_floors: int | None
    status: str
    map_lat: Decimal | None
    map_lon: Decimal | None
    tariff: str
    ask_price: Decimal
    ask_currency: str

    model_config = pydantic.ConfigDict(from_attributes=True)


class ListingOutput(pydantic.BaseModel):
    id: int
    property: PropertyBrief | None = None
    property_id: int
    owner_agreement_id: int | None
    is_active: bool
    is_featured: bool
    description: str | None
    listed_price: Decimal | None
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class ListingMapOutput(pydantic.BaseModel):
    type: str = "FeatureCollection"
    features: list[dict]


class ViewingRequestCreateInput(pydantic.BaseModel):
    full_name: str
    phone: str
    email: str
    preferred_date: date
    message: str | None = None


class ViewingRequestOutput(pydantic.BaseModel):
    id: int
    listing_id: int
    full_name: str
    phone: str
    email: str
    preferred_date: date
    message: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)
