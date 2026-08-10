from django.conf import settings
from django.db.models import Max, Min
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from dmr import Path, Query
from marketplace.models import Listing
from marketplace.services.listings import (
    ListingFilters,
    apply_listing_filters,
    ordered_photos,
    photo_url,
    published_listings_queryset,
)
from property.models import District

from api.v1.marketplace.views import RESPONSE_TIME, _verification_checklist
from api.v1.mobile.home.schemas import (
    MobileHomeFeedQuery,
    MobileListingAmenity,
    MobileListingCard,
    MobileListingDetail,
    MobileListingPhoto,
    MobileListingVerification,
    MobileVerificationItem,
)
from core.api.views import BaseController, DetailPath
from core.constants import FurnishingType, ListingStatus, TariffChoices
from core.utils.pagination import build_paginated_response_from_queryset


def serialize_mobile_listing_card(listing, request) -> dict:
    prop = listing.property
    monthly_price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
    photos = ordered_photos(prop)
    return MobileListingCard(
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
        price=float(monthly_price) if monthly_price is not None else None,
        currency=listing.currency or prop.ask_currency,
        tariff=prop.tariff,
        is_verified=prop.is_verified,
        is_featured=listing.is_featured,
        score=float(prop.score),
        review_count=prop.review_count,
        cover_image_url=photo_url(photos[0], request) if photos else None,
        map_lat=float(prop.map_lat) if prop.map_lat is not None else None,
        map_lon=float(prop.map_lon) if prop.map_lon is not None else None,
    ).model_dump(mode="json")


def serialize_mobile_listing_detail(listing, request) -> dict:
    prop = listing.property
    monthly_price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
    deposit = listing.deposit_amount if listing.deposit_amount is not None else prop.deposit_amount
    photos = ordered_photos(prop)
    amenities = sorted(
        (amenity for amenity in prop.amenities.all() if amenity.is_active),
        key=lambda amenity: (amenity.sort_order, amenity.name),
    )
    return MobileListingDetail(
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
        price=float(monthly_price) if monthly_price is not None else None,
        currency=listing.currency or prop.ask_currency,
        tariff=prop.tariff,
        is_verified=prop.is_verified,
        is_featured=listing.is_featured,
        score=float(prop.score),
        review_count=prop.review_count,
        map_lat=float(prop.map_lat) if prop.map_lat is not None else None,
        map_lon=float(prop.map_lon) if prop.map_lon is not None else None,
        description=listing.description or prop.description or None,
        deposit_amount=float(deposit) if deposit is not None else None,
        minimum_stay=listing.minimum_stay,
        price_includes=listing.price_includes or [],
        response_time=str(RESPONSE_TIME),
        created_at=listing.created_at.isoformat(),
        photos=[
            MobileListingPhoto(
                id=photo.id,
                image_url=photo_url(photo, request),
                caption=photo.caption or None,
                is_primary=photo.is_primary,
                sort_order=photo.sort_order,
            )
            for photo in photos
        ],
        amenities=[
            MobileListingAmenity(
                slug=amenity.slug,
                name=amenity.name,
                icon=amenity.icon or None,
            )
            for amenity in amenities
        ],
        verification=MobileListingVerification(
            is_verified=prop.is_verified,
            checklist=[
                MobileVerificationItem(key=item["key"], label=str(item["label"]))
                for item in _verification_checklist(prop)
            ],
        ),
        can_message=listing.status == ListingStatus.PUBLISHED and listing.deleted_at is None,
        contact_phone=getattr(settings, "PLATFORM_CONTACT_PHONE", "") or None,
    ).model_dump(mode="json")


class MobileHomeListingsView(BaseController):
    auth = ()

    def get(self, parsed_query: Query[MobileHomeFeedQuery]) -> dict:
        filters = ListingFilters(**parsed_query.model_dump())
        qs = apply_listing_filters(published_listings_queryset(), filters)
        paginated = build_paginated_response_from_queryset(
            qs,
            parsed_query.page,
            parsed_query.per_page,
            lambda listing: serialize_mobile_listing_card(listing, self.request),
        )
        return self.ok(paginated)


class MobileHomeListingDetailView(BaseController):
    auth = ()

    def get(self, parsed_path: Path[DetailPath]) -> dict:
        listing = get_object_or_404(
            Listing.global_objects.select_related("property__district").prefetch_related(
                "property__photos", "property__amenities"
            ),
            pk=parsed_path.pk,
        )
        return self.ok(serialize_mobile_listing_detail(listing, self.request))


class MobileHomeFiltersView(BaseController):
    auth = ()

    def get(self) -> dict:
        published_qs = published_listings_queryset()
        price_bounds = published_qs.aggregate(min=Min("_price"), max=Max("_price"))
        room_bounds = published_qs.aggregate(min=Min("property__rooms"), max=Max("property__rooms"))

        districts = [{"id": district.id, "name": district.name} for district in District.objects.order_by("name")]
        tariffs = [{"value": value, "label": str(_(label))} for value, label in TariffChoices.CHOICES]
        furnishings = [{"value": value, "label": str(_(label))} for value, label in FurnishingType.CHOICES]
        price = {
            "min": float(price_bounds["min"]) if price_bounds["min"] is not None else None,
            "max": float(price_bounds["max"]) if price_bounds["max"] is not None else None,
        }
        rooms = {
            "min": int(room_bounds["min"]) if room_bounds["min"] is not None else None,
            "max": int(room_bounds["max"]) if room_bounds["max"] is not None else None,
        }
        return self.ok(
            {
                "districts": districts,
                "tariffs": tariffs,
                "furnishings": furnishings,
                "price": price,
                "rooms": rooms,
            }
        )
