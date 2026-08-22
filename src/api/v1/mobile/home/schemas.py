import math
from typing import Literal

import pydantic


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = value.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must contain exactly four comma-separated numbers")

    try:
        min_lon, min_lat, max_lon, max_lat = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError("bbox must contain exactly four comma-separated numbers") from exc

    coordinates = (min_lon, min_lat, max_lon, max_lat)
    if not all(math.isfinite(coordinate) for coordinate in coordinates):
        raise ValueError("bbox coordinates must be finite")
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        raise ValueError("bbox longitude must be between -180 and 180")
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise ValueError("bbox latitude must be between -90 and 90")
    if min_lon >= max_lon:
        raise ValueError("bbox minimum longitude must be less than maximum longitude")
    if min_lat >= max_lat:
        raise ValueError("bbox minimum latitude must be less than maximum latitude")
    return coordinates


class MobileHomeFeedQuery(pydantic.BaseModel):
    page: int = 1
    per_page: int = 20
    q: str | None = None
    district_id: int | None = None
    price_min: float | None = None
    price_max: float | None = None
    rooms_min: int | None = None
    rooms_max: int | None = None
    verified: bool | None = None
    furnishing: str | None = None
    tariff: str | None = None
    property_type: str | None = None
    sort: Literal["newest", "price_asc", "price_desc", "score_desc", "rating_desc"] | None = None


class MobileHomeMapQuery(pydantic.BaseModel):
    bbox: str
    favorites_only: bool = False
    q: str | None = None
    district_id: int | None = None
    property_type: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    rooms_min: int | None = None
    rooms_max: int | None = None
    verified: bool | None = None
    furnishing: str | None = None
    tariff: str | None = None

    @pydantic.field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: str) -> str:
        parse_bbox(value)
        return value


class MobileListingCard(pydantic.BaseModel):
    id: int
    property_id: int
    title: str
    district: str | None
    address: str
    property_type: str
    rooms: int | None
    area_sqm: int | None
    floor: int | None
    total_floors: int | None
    furnishing: str
    price: float | None
    currency: str
    tariff: str
    is_verified: bool
    is_featured: bool
    score: float
    review_count: int
    cover_image_url: str | None
    cover_preview_url: str | None
    cover_display_url: str | None
    map_lat: float | None
    map_lon: float | None
    is_favorite: bool = False


class MobileListingMapItem(MobileListingCard):
    map_lat: float | None = None
    map_lon: float | None = None
    contact_phone: str | None = None


class MobileListingMapResponse(pydantic.BaseModel):
    items: list[MobileListingMapItem]
    count: int
    truncated: bool


class MobileListingPhoto(pydantic.BaseModel):
    id: int
    image_url: str
    preview_url: str | None
    display_url: str | None
    caption: str | None
    is_primary: bool
    sort_order: int


class MobileListingAmenity(pydantic.BaseModel):
    slug: str
    name: str
    icon: str | None


class MobileVerificationItem(pydantic.BaseModel):
    key: str
    label: str


class MobileListingVerification(pydantic.BaseModel):
    is_verified: bool
    checklist: list[MobileVerificationItem]


class MobileListingDetail(pydantic.BaseModel):
    id: int
    property_id: int
    title: str
    district: str | None
    address: str
    property_type: str
    rooms: int | None
    area_sqm: int | None
    floor: int | None
    total_floors: int | None
    furnishing: str
    price: float | None
    currency: str
    tariff: str
    is_verified: bool
    is_featured: bool
    score: float
    review_count: int
    map_lat: float | None
    map_lon: float | None
    description: str | None
    deposit_amount: float | None
    minimum_stay: int | None
    price_includes: list[str]
    response_time: str
    created_at: str
    photos: list[MobileListingPhoto]
    amenities: list[MobileListingAmenity]
    verification: MobileListingVerification
    can_message: bool
    contact_phone: str | None
    booking: dict
