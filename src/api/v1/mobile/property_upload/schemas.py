from decimal import Decimal
from typing import Literal

import pydantic
from property.services.validation import validate_floor_bounds


class ChoiceItem(pydantic.BaseModel):
    value: str
    label: str


class DistrictItem(pydantic.BaseModel):
    id: int
    name: str
    city: str


class AmenityItem(pydantic.BaseModel):
    slug: str
    name: str
    icon: str


class PublicOfferItem(pydantic.BaseModel):
    id: int | None = None
    version: str | None = None
    body: str | None = None


class UserProfileItem(pydantic.BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None


class MobilePropertyUploadConfigOutput(pydantic.BaseModel):
    property_types: list[ChoiceItem]
    districts: list[DistrictItem]
    furnishings: list[ChoiceItem]
    amenities: list[AmenityItem]
    minimum_stays: list[int]
    price_includes: list[ChoiceItem]
    currencies: list[str]
    public_offer: PublicOfferItem
    user_profile: UserProfileItem | None = None


class MobilePropertyContactInput(pydantic.BaseModel):
    first_name: str
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None


class MobilePropertyUploadInput(pydantic.BaseModel):
    name: str | None = None
    property_type: str
    district_id: int
    rooms: int = pydantic.Field(ge=1)
    floor: int = pydantic.Field(ge=0)
    total_floors: int | None = pydantic.Field(default=None, ge=0)
    area_sqm: int = pydantic.Field(ge=1)
    furnishing: str
    description: str | None = None
    amenities: list[str] = pydantic.Field(default_factory=list)
    monthly_price: Decimal = pydantic.Field(ge=0)
    deposit_amount: Decimal | None = None
    currency: str = "USD"
    minimum_stay: int | None = None
    price_includes: list[str] = pydantic.Field(default_factory=list)
    content_locale: Literal["en", "uz", "ru"] | None = None
    accept_offer: bool
    contact: MobilePropertyContactInput | None = None

    @pydantic.model_validator(mode="after")
    def validate_floor_bounds(self):
        validate_floor_bounds(self.floor, self.total_floors)
        return self


class MobilePropertyUploadOutput(pydantic.BaseModel):
    id: int
    property_id: int
    status: str
    message: str
