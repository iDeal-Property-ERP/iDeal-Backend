import math
from typing import Any, Literal

import pydantic

from core.api.schemas import APIModel


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except TypeError, ValueError:
        return default


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


class MobileHomeFeedQuery(APIModel):
    page: int = pydantic.Field(default=1, ge=1)
    per_page: int = pydantic.Field(default=20, ge=1, le=100)
    q: str | None = None
    district_id: int | None = pydantic.Field(default=None, ge=1)
    price_min: float | None = pydantic.Field(default=None, ge=0)
    price_max: float | None = pydantic.Field(default=None, ge=0)
    rooms_min: int | None = pydantic.Field(default=None, ge=0)
    rooms_max: int | None = pydantic.Field(default=None, ge=0)
    verified: bool | None = None
    furnishing: Literal["furnished", "semi_furnished", "unfurnished"] | None = None
    tariff: Literal["standard", "comfort", "premium"] | None = None
    property_type: Literal["apartment", "house", "studio", "room"] | None = None
    sort: Literal["newest", "price_asc", "price_desc", "score_desc", "rating_desc"] | None = None

    @pydantic.model_validator(mode="after")
    def validate_ranges(self):
        if self.price_min is not None and self.price_max is not None and self.price_min > self.price_max:
            raise ValueError("price_min cannot exceed price_max")
        if self.rooms_min is not None and self.rooms_max is not None and self.rooms_min > self.rooms_max:
            raise ValueError("rooms_min cannot exceed rooms_max")
        return self


class MobileHomeMapQuery(APIModel):
    bbox: str
    favorites_only: bool = False
    q: str | None = None
    district_id: int | None = pydantic.Field(default=None, ge=1)
    property_type: Literal["apartment", "house", "studio", "room"] | None = None
    price_min: float | None = pydantic.Field(default=None, ge=0)
    price_max: float | None = pydantic.Field(default=None, ge=0)
    rooms_min: int | None = pydantic.Field(default=None, ge=0)
    rooms_max: int | None = pydantic.Field(default=None, ge=0)
    verified: bool | None = None
    furnishing: Literal["furnished", "semi_furnished", "unfurnished"] | None = None
    tariff: Literal["standard", "comfort", "premium"] | None = None

    @pydantic.field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: str) -> str:
        parse_bbox(value)
        return value

    @pydantic.model_validator(mode="after")
    def validate_ranges(self):
        if self.price_min is not None and self.price_max is not None and self.price_min > self.price_max:
            raise ValueError("price_min cannot exceed price_max")
        if self.rooms_min is not None and self.rooms_max is not None and self.rooms_min > self.rooms_max:
            raise ValueError("rooms_min cannot exceed rooms_max")
        return self


class MobileListingCard(APIModel):
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

    @classmethod
    def from_listing(cls, listing, *, request, favorite_ids: set[int] | None = None):
        """Build output from a queryset that already selects/prefetches relations."""
        from marketplace.services.listings import ordered_photos, photo_url, photo_variant_url

        prop = listing.property
        monthly_price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
        photos = ordered_photos(prop)
        cover_photo = photos[0] if photos else None
        return cls(
            id=listing.id,
            property_id=listing.property_id,
            title=prop.name,
            district=prop.district.name if prop.district else None,
            address=prop.address,
            property_type=prop.property_type,
            rooms=prop.rooms,
            area_sqm=prop.area_sqm,
            floor=prop.floor,
            total_floors=prop.total_floors,
            furnishing=prop.furnishing,
            price=_safe_float(monthly_price),
            currency=listing.currency or prop.ask_currency,
            tariff=prop.tariff,
            is_verified=prop.is_verified,
            is_featured=listing.is_featured,
            score=_safe_float(prop.score, 0.0) or 0.0,
            review_count=prop.review_count,
            cover_image_url=photo_url(cover_photo, request) if cover_photo else None,
            cover_preview_url=photo_variant_url(cover_photo, "preview_image", request) if cover_photo else None,
            cover_display_url=photo_variant_url(cover_photo, "display_image", request) if cover_photo else None,
            map_lat=_safe_float(prop.map_lat),
            map_lon=_safe_float(prop.map_lon),
            is_favorite=listing.id in (favorite_ids or set()),
        )


class MobileListingMapItem(MobileListingCard):
    map_lat: float | None = None
    map_lon: float | None = None
    contact_phone: str | None = None

    @classmethod
    def from_listing(cls, listing, *, request, favorite_ids: set[int] | None = None, contact_phone: str | None = None):
        from django.conf import settings

        card = MobileListingCard.from_listing(listing, request=request, favorite_ids=favorite_ids)
        return cls(
            **card.__dict__,
            contact_phone=contact_phone or getattr(settings, "PLATFORM_CONTACT_PHONE", "") or None,
        )


class MobileListingMapResponse(APIModel):
    items: list[MobileListingMapItem]
    count: int
    truncated: bool


class MobileListingPhoto(APIModel):
    id: int
    image_url: str
    preview_url: str | None
    display_url: str | None
    caption: str | None
    is_primary: bool
    sort_order: int


class MobileListingAmenity(APIModel):
    slug: str
    name: str
    icon: str | None


class MobileVerificationItem(APIModel):
    key: str
    label: str


class MobileListingVerification(APIModel):
    is_verified: bool
    checklist: list[MobileVerificationItem]


class MobileListingDetail(APIModel):
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

    @classmethod
    def from_listing(cls, listing, *, request, contact_phone: str | None = None):
        from django.conf import settings
        from marketplace.services.booking import BookingService
        from marketplace.services.listings import ordered_photos, photo_url, photo_variant_url
        from marketplace.services.presentation import RESPONSE_TIME, verification_checklist

        prop = listing.property
        monthly_price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
        deposit = listing.deposit_amount if listing.deposit_amount is not None else prop.deposit_amount
        photos = ordered_photos(prop)
        amenities = sorted(
            (amenity for amenity in prop.amenities.all() if amenity.is_active),
            key=lambda amenity: (amenity.sort_order, amenity.name),
        )
        return cls(
            id=listing.id,
            property_id=listing.property_id,
            title=prop.name,
            district=prop.district.name if prop.district else None,
            address=prop.address,
            property_type=prop.property_type,
            rooms=prop.rooms,
            area_sqm=prop.area_sqm,
            floor=prop.floor,
            total_floors=prop.total_floors,
            furnishing=prop.furnishing,
            price=_safe_float(monthly_price),
            currency=listing.currency or prop.ask_currency,
            tariff=prop.tariff,
            is_verified=prop.is_verified,
            is_featured=listing.is_featured,
            score=_safe_float(prop.score, 0.0) or 0.0,
            review_count=prop.review_count,
            map_lat=_safe_float(prop.map_lat),
            map_lon=_safe_float(prop.map_lon),
            description=listing.description or prop.description or None,
            deposit_amount=_safe_float(deposit),
            minimum_stay=listing.minimum_stay,
            price_includes=listing.price_includes or [],
            response_time=str(RESPONSE_TIME),
            created_at=listing.created_at.isoformat(),
            photos=[
                MobileListingPhoto(
                    id=photo.id,
                    image_url=photo_url(photo, request),
                    preview_url=photo_variant_url(photo, "preview_image", request),
                    display_url=photo_variant_url(photo, "display_image", request),
                    caption=photo.caption or None,
                    is_primary=photo.is_primary,
                    sort_order=photo.sort_order,
                )
                for photo in photos
            ],
            amenities=[MobileListingAmenity(slug=a.slug, name=a.name, icon=a.icon or None) for a in amenities],
            verification=MobileListingVerification(
                is_verified=prop.is_verified,
                checklist=[MobileVerificationItem(**item) for item in verification_checklist(prop)],
            ),
            can_message=listing.status == "published" and listing.deleted_at is None,
            contact_phone=contact_phone or getattr(settings, "PLATFORM_CONTACT_PHONE", "") or None,
            booking=BookingService().eligibility(listing),
        )


class MobileRecommendedListingsResponse(APIModel):
    items: list[MobileListingCard]
    count: int


class MobileActivityRecordRequest(APIModel):
    type: Literal["search", "view"]
    query: str | None = None
    filters: dict[str, Any] | None = None
    listing_id: int | None = None

    @pydantic.model_validator(mode="after")
    def validate_payload(self):
        if self.type == "view":
            if self.listing_id is None:
                raise ValueError("listing_id is required when type is 'view'")
        elif self.type == "search":
            has_query = bool((self.query or "").strip())
            has_filters = bool(
                self.filters
                and isinstance(self.filters, dict)
                and any(v is not None and v != "" for v in self.filters.values())
            )
            if not has_query and not has_filters:
                raise ValueError("query or filters is required when type is 'search'")
        return self


class MobileActivityRecordResponse(APIModel):
    recorded: bool = True
