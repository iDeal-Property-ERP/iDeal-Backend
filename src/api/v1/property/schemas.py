from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic
from django.utils.translation import gettext_lazy as _
from pydantic import field_validator


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


class PropertyPhotoOutput(pydantic.BaseModel):
    id: int
    image_url: str
    caption: str | None = None
    is_primary: bool
    sort_order: int

    model_config = pydantic.ConfigDict(from_attributes=True)


class VerificationVisitOutput(pydantic.BaseModel):
    id: int
    scheduled_for: datetime
    status: str
    completed_at: datetime | None
    notes: str

    model_config = pydantic.ConfigDict(from_attributes=True)


class PropertyOutput(pydantic.BaseModel):
    id: int
    name: str
    address: str
    # Nullable so DRAFT properties (saved partially) serialize cleanly.
    district: DistrictOutput | None
    rooms: int | None
    area_sqm: int | None
    floor: int | None
    total_floors: int | None
    owner: OwnerOutput | None
    status: str
    is_verified: bool
    score: Decimal
    map_lat: Decimal | None
    map_lon: Decimal | None
    description: str | None
    tariff: str
    ask_price: Decimal | None
    ask_currency: str
    owner_guaranteed_price: Decimal | None
    owner_guaranteed_currency: str
    tenant_charge_price: Decimal | None
    tenant_charge_currency: str
    vacant_since: date | None
    vacant_days: int
    # Injected by the view (reverse managers can't be validated from attributes);
    # aliased so `model_validate(property)` doesn't try to read the manager.
    photos: list[PropertyPhotoOutput] = pydantic.Field(default=[], validation_alias="_photos")
    verification: VerificationVisitOutput | None = pydantic.Field(default=None, validation_alias="_verification")
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class PropertyCreateInput(pydantic.BaseModel):
    name: str
    address: str
    district_id: int
    rooms: int = pydantic.Field(ge=0)
    area_sqm: int = pydantic.Field(ge=0)
    floor: int = pydantic.Field(ge=0)
    total_floors: int | None = pydantic.Field(default=None, ge=0)
    owner_id: int
    status: str = "vacant"
    score: Decimal = Decimal("0.0")
    map_lat: Decimal | None = None
    map_lon: Decimal | None = None
    description: str | None = None
    tariff: str = "standard"
    ask_price: Decimal = pydantic.Field(ge=0)
    ask_currency: str = "USD"
    owner_guaranteed_price: Decimal = pydantic.Field(ge=0)
    owner_guaranteed_currency: str = "USD"
    tenant_charge_price: Decimal = pydantic.Field(ge=0)
    tenant_charge_currency: str = "USD"
    vacant_since: date | None = None
    vacant_days: int = pydantic.Field(default=0, ge=0)

    @field_validator("district_id")
    @classmethod
    def check_district_exists(cls, v: int) -> int:
        from property.models import District

        if not District.objects.filter(id=v).exists():
            raise ValueError(_("District with id %s does not exist") % v)
        return v

    @field_validator("owner_id")
    @classmethod
    def check_owner_exists(cls, v: int) -> int:
        from account.models import User

        from core.constants import UserRole

        if not User.objects.filter(id=v, role=UserRole.OWNER).exists():
            raise ValueError(_("No active owner found with id %s") % v)
        return v


class PropertyUpdateInput(pydantic.BaseModel):
    name: str | None = None
    address: str | None = None
    district_id: int | None = None
    rooms: int | None = pydantic.Field(default=None, ge=0)
    area_sqm: int | None = pydantic.Field(default=None, ge=0)
    floor: int | None = pydantic.Field(default=None, ge=0)
    total_floors: int | None = pydantic.Field(default=None, ge=0)
    owner_id: int | None = None
    status: str | None = None
    score: Decimal | None = None
    map_lat: Decimal | None = None
    map_lon: Decimal | None = None
    description: str | None = None
    tariff: str | None = None
    ask_price: Decimal | None = pydantic.Field(default=None, ge=0)
    ask_currency: str | None = None
    owner_guaranteed_price: Decimal | None = pydantic.Field(default=None, ge=0)
    owner_guaranteed_currency: str | None = None
    tenant_charge_price: Decimal | None = pydantic.Field(default=None, ge=0)
    tenant_charge_currency: str | None = None
    vacant_since: date | None = None
    vacant_days: int | None = pydantic.Field(default=None, ge=0)

    @field_validator("district_id")
    @classmethod
    def check_district_exists(cls, v: int | None) -> int | None:
        if v is None:
            return v
        from property.models import District

        if not District.objects.filter(id=v).exists():
            raise ValueError(_("District with id %s does not exist") % v)
        return v

    @field_validator("owner_id")
    @classmethod
    def check_owner_exists(cls, v: int | None) -> int | None:
        if v is None:
            return v
        from account.models import User

        if not User.objects.filter(id=v).exists():
            raise ValueError(_("Owner with id %s does not exist") % v)
        return v


class PropertyDraftCreateInput(PropertyUpdateInput):
    """A draft may be created with any subset of fields; name defaults so the
    row is identifiable in the workbench."""

    name: str = "Untitled property"


class PropertyPublishInput(pydantic.BaseModel):
    schedule_verification_at: datetime | None = None


class PropertyPhotoReorderItem(pydantic.BaseModel):
    id: int
    sort_order: int = 0
    is_primary: bool = False
    caption: str | None = None


class PropertyPhotoReorderInput(pydantic.BaseModel):
    items: list[PropertyPhotoReorderItem]


class VerificationVisitCreateInput(pydantic.BaseModel):
    scheduled_for: datetime
    notes: str = ""
