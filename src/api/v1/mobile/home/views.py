from http import HTTPStatus
from typing import Any

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Max, Min, Subquery
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from dmr.exceptions import NotAuthenticatedError
from dmr.pagination import Page, Paginated
from marketplace.models import Listing
from marketplace.services.booking import BookingService
from marketplace.services.favorites import FavoriteListingService
from marketplace.services.listings import (
    ListingFilters,
    apply_listing_filters,
    ordered_photos,
    photo_url,
    photo_variant_url,
    published_listings_queryset,
)
from marketplace.services.recommendations import RecommendationService
from property.models import District

from api.v1.marketplace.views import RESPONSE_TIME, _verification_checklist
from api.v1.mobile.home.schemas import (
    MobileActivityRecordRequest,
    MobileActivityRecordResponse,
    MobileHomeFeedQuery,
    MobileHomeMapQuery,
    MobileListingAmenity,
    MobileListingCard,
    MobileListingDetail,
    MobileListingMapItem,
    MobileListingMapResponse,
    MobileListingPhoto,
    MobileListingVerification,
    MobileRecommendedListingsResponse,
    MobileVerificationItem,
    parse_bbox,
)
from core.api.permissions import BlacklistAwareJWTSyncAuth
from core.api.views import BaseController, DetailPath
from core.constants import FurnishingType, ListingStatus, PropertyType, TariffChoices

_OPTIONAL_AUTH = BlacklistAwareJWTSyncAuth()


def _safe_float(val: Any, default: float | None = None) -> float | None:
    if val is None:
        return default
    try:
        return float(val)
    except ValueError, TypeError:
        return default


def _safe_int(val: Any, default: int | None = None) -> int | None:
    if val is None:
        return default
    try:
        return int(val)
    except ValueError, TypeError:
        return default


def get_optional_authenticated_user(request):
    raw_token = _OPTIONAL_AUTH.get_token_from_request(request)
    if not raw_token:
        return None

    parts = raw_token.split(" ")
    if len(parts) != 2 or parts[0].casefold() != _OPTIONAL_AUTH.auth_scheme.casefold():
        return None

    try:
        token = _OPTIONAL_AUTH.decode_token(parts[1])
        user = _OPTIONAL_AUTH.get_user(token)
        _OPTIONAL_AUTH.check_auth(user, token)
    except NotAuthenticatedError:
        return None
    return user


def build_mobile_listing_paginated_response(qs, page: int, per_page: int, request, user=None) -> Paginated:
    paginator = Paginator(qs, per_page)
    django_page = paginator.get_page(page)
    listings = list(django_page.object_list)
    favorite_ids = FavoriteListingService.favorite_ids_for_listings(user, [listing.id for listing in listings])
    return Paginated(
        count=paginator.count,
        num_pages=paginator.num_pages,
        per_page=paginator.per_page,
        page=Page(
            number=django_page.number,
            object_list=[
                serialize_mobile_listing_card(listing, request, favorite_ids=favorite_ids) for listing in listings
            ],
        ),
    )


def serialize_mobile_listing_card(listing, request, *, favorite_ids: set[int] | None = None) -> dict:
    prop = listing.property
    monthly_price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
    photos = ordered_photos(prop)
    cover_photo = photos[0] if photos else None
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
        booking=BookingService.eligibility(listing),
    ).model_dump(mode="json")


def serialize_mobile_listing_map_item(listing, request, *, favorite_ids: set[int] | None = None) -> dict:
    card = serialize_mobile_listing_card(listing, request, favorite_ids=favorite_ids)
    return MobileListingMapItem(
        **card,
        contact_phone=getattr(settings, "PLATFORM_CONTACT_PHONE", "") or None,
    ).model_dump(mode="json")


class MobileHomeListingsView(BaseController):
    auth = ()

    def get(self, parsed_query: Query[MobileHomeFeedQuery]) -> dict:
        user = get_optional_authenticated_user(self.request)
        filters = ListingFilters(**parsed_query.model_dump())
        qs = apply_listing_filters(published_listings_queryset(), filters, include_future_managed=True)
        paginated = build_mobile_listing_paginated_response(
            qs, parsed_query.page, parsed_query.per_page, self.request, user=user
        )
        return self.ok(paginated)


class MobileHomeListingMapView(BaseController):
    auth = ()
    MAX_ITEMS = 500

    def get(self, parsed_query: Query[MobileHomeMapQuery]) -> dict:
        user = get_optional_authenticated_user(self.request)
        if parsed_query.favorites_only and user is None:
            return self.fail(
                error="Not authenticated",
                message="Not authenticated",
                status_code=HTTPStatus.UNAUTHORIZED,
            )
        min_lon, min_lat, max_lon, max_lat = parse_bbox(parsed_query.bbox)
        filters = ListingFilters(**parsed_query.model_dump(exclude={"bbox", "favorites_only"}))
        qs = apply_listing_filters(published_listings_queryset(), filters, include_future_managed=True)
        if parsed_query.favorites_only:
            qs = qs.filter(pk__in=Subquery(FavoriteListingService.favorite_listing_ids(user)))
        qs = (
            qs.filter(
                property__map_lat__gte=min_lat,
                property__map_lat__lte=max_lat,
                property__map_lon__gte=min_lon,
                property__map_lon__lte=max_lon,
            )
            .exclude(property__map_lat__isnull=True)
            .exclude(property__map_lon__isnull=True)
            .order_by("-is_featured", "-created_at", "-id")
        )
        count = qs.count()
        listings = list(qs[: self.MAX_ITEMS])
        favorite_ids = FavoriteListingService.favorite_ids_for_listings(user, [listing.id for listing in listings])
        items = [
            serialize_mobile_listing_map_item(listing, self.request, favorite_ids=favorite_ids) for listing in listings
        ]
        data = MobileListingMapResponse(
            items=items,
            count=count,
            truncated=count > self.MAX_ITEMS,
        )
        return self.ok(data.model_dump(mode="json"))


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


class MobileHomeBookingOptionsView(BaseController):
    auth = ()

    def get(self, parsed_path: Path[DetailPath]) -> dict:
        listing = get_object_or_404(
            Listing.objects.select_related("property", "owner_agreement"),
            pk=parsed_path.pk,
        )
        return self.ok(BookingService.booking_options(listing))


class MobileHomeFiltersView(BaseController):
    auth = ()

    def get(self) -> dict:
        published_qs = published_listings_queryset()
        price_bounds = published_qs.aggregate(min=Min("_price"), max=Max("_price"))
        room_bounds = published_qs.aggregate(min=Min("property__rooms"), max=Max("property__rooms"))

        districts = [{"id": district.id, "name": district.name} for district in District.objects.order_by("name")]
        tariffs = [{"value": value, "label": str(_(label))} for value, label in TariffChoices.CHOICES]
        furnishings = [{"value": value, "label": str(_(label))} for value, label in FurnishingType.CHOICES]
        property_types = [{"value": value, "label": str(_(label))} for value, label in PropertyType.CHOICES]
        price = {
            "min": _safe_float(price_bounds["min"]),
            "max": _safe_float(price_bounds["max"]),
        }
        rooms = {
            "min": _safe_int(room_bounds["min"]),
            "max": _safe_int(room_bounds["max"]),
        }
        return self.ok(
            {
                "districts": districts,
                "tariffs": tariffs,
                "furnishings": furnishings,
                "property_types": property_types,
                "price": price,
                "rooms": rooms,
            }
        )


class MobileHomeRecommendedListingsView(BaseController):
    def get(self) -> dict:
        user = self.request.user
        recommendations = RecommendationService.get_recommendations(user, limit=6)
        favorite_ids = FavoriteListingService.favorite_ids_for_listings(
            user, [listing.id for listing in recommendations]
        )
        items = [
            serialize_mobile_listing_card(listing, self.request, favorite_ids=favorite_ids)
            for listing in recommendations
        ]
        data = MobileRecommendedListingsResponse(
            items=items,
            count=len(items),
        )
        return self.ok(data.model_dump(mode="json"))

    def post(self, parsed_body: Body[MobileActivityRecordRequest]) -> dict:
        user = self.request.user
        if parsed_body.type == "search":
            try:
                RecommendationService.record_search(user, parsed_body.query, parsed_body.filters)
            except ValueError as exc:
                return self.fail(error=str(exc), status_code=HTTPStatus.BAD_REQUEST)
        elif parsed_body.type == "view":
            try:
                if parsed_body.listing_id is None:
                    return self.fail(error="listing_id_required", status_code=HTTPStatus.BAD_REQUEST)
                RecommendationService.record_view(user, parsed_body.listing_id)
            except Http404, Listing.DoesNotExist:
                return self.fail(error="listing_not_found", status_code=HTTPStatus.NOT_FOUND)
        return self.ok(MobileActivityRecordResponse(recorded=True).model_dump(mode="json"))
