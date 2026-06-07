from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic


class DistrictOutput(pydantic.BaseModel):
    id: int
    name: str
    city: str

    model_config = pydantic.ConfigDict(from_attributes=True)


class OwnerOutput(pydantic.BaseModel):
    id: int
    first_name: str
    last_name: str | None

    model_config = pydantic.ConfigDict(from_attributes=True)


class PropertyOutput(pydantic.BaseModel):
    id: int
    name: str
    address: str
    district: DistrictOutput
    rooms: int
    area_sqm: int
    floor: int
    total_floors: int | None
    owner: OwnerOutput
    status: str
    score: Decimal
    map_lat: Decimal | None
    map_lon: Decimal | None
    description: str | None
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


class PropertyCreateInput(pydantic.BaseModel):
    name: str
    address: str
    district_id: int
    rooms: int
    area_sqm: int
    floor: int
    total_floors: int | None = None
    owner_id: int
    status: str = "vacant"
    score: Decimal = Decimal("0.0")
    map_lat: Decimal | None = None
    map_lon: Decimal | None = None
    description: str | None = None
    tariff: str = "standard"
    ask_price: Decimal
    ask_currency: str = "USD"
    owner_guaranteed_price: Decimal
    owner_guaranteed_currency: str = "USD"
    tenant_charge_price: Decimal
    tenant_charge_currency: str = "USD"
    vacant_since: date | None = None
    vacant_days: int = 0


class PropertyUpdateInput(pydantic.BaseModel):
    name: str | None = None
    address: str | None = None
    district_id: int | None = None
    rooms: int | None = None
    area_sqm: int | None = None
    floor: int | None = None
    total_floors: int | None = None
    owner_id: int | None = None
    status: str | None = None
    score: Decimal | None = None
    map_lat: Decimal | None = None
    map_lon: Decimal | None = None
    description: str | None = None
    tariff: str | None = None
    ask_price: Decimal | None = None
    ask_currency: str | None = None
    owner_guaranteed_price: Decimal | None = None
    owner_guaranteed_currency: str | None = None
    tenant_charge_price: Decimal | None = None
    tenant_charge_currency: str | None = None
    vacant_since: date | None = None
    vacant_days: int | None = None
