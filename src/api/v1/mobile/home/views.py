from django.db.models import Max, Min
from django.utils.translation import gettext_lazy as _
from dmr import Query
from marketplace.services.listings import (
    ListingFilters,
    apply_listing_filters,
    ordered_photos,
    photo_url,
    published_listings_queryset,
)
from property.models import District

from api.v1.mobile.home.schemas import MobileHomeFeedQuery, MobileListingCard
from core.api.views import BaseController
from core.constants import FurnishingType, TariffChoices
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
