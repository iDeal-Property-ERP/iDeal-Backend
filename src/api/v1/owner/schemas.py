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
