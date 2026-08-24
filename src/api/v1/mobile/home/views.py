from http import HTTPStatus

from django.db.models import Max, Min, Subquery
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query, modify
from dmr.exceptions import NotAuthenticatedError
from marketplace.models import Listing
from marketplace.services.booking import BookingService
from marketplace.services.favorites import FavoriteListingService
from marketplace.services.listings import (
    ListingDiscoveryService,
    ListingFilters,
    published_listings_queryset,
)
from marketplace.services.recommendations import RecommendationService
from property.models import District

from api.v1.mobile.home.schemas import (
    MobileActivityRecordRequest,
    MobileActivityRecordResponse,
    MobileHomeFeedQuery,
    MobileHomeMapQuery,
    MobileListingCard,
    MobileListingDetail,
    MobileListingMapItem,
    MobileListingMapResponse,
    MobileRecommendedListingsResponse,
    parse_bbox,
)
from core.api.permissions import BlacklistAwareJWTSyncAuth
from core.api.schemas import Pagination, SuccessResponse
from core.api.views import BaseController, DetailPath
from core.constants import FurnishingType, PropertyType, TariffChoices
from core.utils.pagination import build_paginated_response_from_queryset

_OPTIONAL_AUTH = BlacklistAwareJWTSyncAuth()


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


class MobileHomeListingsView(BaseController):
    auth = ()

    def get(self, parsed_query: Query[MobileHomeFeedQuery]) -> SuccessResponse[Pagination[MobileListingCard]]:
        user = get_optional_authenticated_user(self.request)
        filters = ListingFilters(**parsed_query.model_dump())
        discovery = self.get_service(ListingDiscoveryService)
        favorites = self.get_service(FavoriteListingService)
        qs = discovery.filter(published_listings_queryset(), filters, request=self.request, include_future_managed=True)

        def cards(listings):
            favorite_ids = favorites.favorite_ids_for_listings(user, [listing.id for listing in listings])
            return [
                MobileListingCard.from_listing(listing, request=self.request, favorite_ids=favorite_ids)
                for listing in listings
            ]

        paginated = build_paginated_response_from_queryset(
            qs, parsed_query.page, parsed_query.per_page, MobileListingCard.from_listing, serialize_page=cards
        )
        return self.ok(paginated)


class MobileHomeListingMapView(BaseController):
    auth = ()
    MAX_ITEMS = 500

    def get(self, parsed_query: Query[MobileHomeMapQuery]) -> SuccessResponse[MobileListingMapResponse]:
        user = get_optional_authenticated_user(self.request)
        if parsed_query.favorites_only and user is None:
            return self.fail(
                error="Not authenticated",
                message="Not authenticated",
                status_code=HTTPStatus.UNAUTHORIZED,
            )
        min_lon, min_lat, max_lon, max_lat = parse_bbox(parsed_query.bbox)
        filters = ListingFilters(**parsed_query.model_dump(exclude={"bbox", "favorites_only"}))
        discovery = self.get_service(ListingDiscoveryService)
        favorites = self.get_service(FavoriteListingService)
        qs = discovery.filter(published_listings_queryset(), filters, request=self.request, include_future_managed=True)
        if parsed_query.favorites_only:
            qs = qs.filter(pk__in=Subquery(favorites.favorite_listing_ids(user)))
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
        favorite_ids = favorites.favorite_ids_for_listings(user, [listing.id for listing in listings])
        items = [
            MobileListingMapItem.from_listing(listing, request=self.request, favorite_ids=favorite_ids)
            for listing in listings
        ]
        data = MobileListingMapResponse(
            items=items,
            count=count,
            truncated=count > self.MAX_ITEMS,
        )
        return self.ok(data)


class MobileHomeListingDetailView(BaseController):
    auth = ()

    def get(self, parsed_path: Path[DetailPath]) -> SuccessResponse[MobileListingDetail]:
        listing = get_object_or_404(
            Listing.global_objects.select_related("property__district").prefetch_related(
                "property__photos", "property__amenities"
            ),
            pk=parsed_path.pk,
        )
        return self.ok(MobileListingDetail.from_listing(listing, request=self.request))


class MobileHomeBookingOptionsView(BaseController):
    auth = ()

    def get(self, parsed_path: Path[DetailPath]) -> SuccessResponse[dict]:
        listing = get_object_or_404(
            Listing.objects.select_related("property", "owner_agreement"),
            pk=parsed_path.pk,
        )
        return self.ok(BookingService.booking_options(listing))


class MobileHomeFiltersView(BaseController):
    auth = ()

    def get(self) -> SuccessResponse[dict]:
        published_qs = published_listings_queryset()
        price_bounds = published_qs.aggregate(min=Min("_price"), max=Max("_price"))
        room_bounds = published_qs.aggregate(min=Min("property__rooms"), max=Max("property__rooms"))

        districts = [{"id": district.id, "name": district.name} for district in District.objects.order_by("name")]
        tariffs = [{"value": value, "label": str(_(label))} for value, label in TariffChoices.CHOICES]
        furnishings = [{"value": value, "label": str(_(label))} for value, label in FurnishingType.CHOICES]
        property_types = [{"value": value, "label": str(_(label))} for value, label in PropertyType.CHOICES]
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
                "property_types": property_types,
                "price": price,
                "rooms": rooms,
            }
        )


class MobileHomeRecommendedListingsView(BaseController):
    def get(self) -> SuccessResponse[MobileRecommendedListingsResponse]:
        user = self.request.user
        recommendations_service = self.get_service(RecommendationService)
        favorites = self.get_service(FavoriteListingService)
        recommendations = recommendations_service.get_recommendations(user, limit=6)
        favorite_ids = favorites.favorite_ids_for_listings(user, [listing.id for listing in recommendations])
        items = [
            MobileListingCard.from_listing(listing, request=self.request, favorite_ids=favorite_ids)
            for listing in recommendations
        ]
        data = MobileRecommendedListingsResponse(
            items=items,
            count=len(items),
        )
        return self.ok(data)

    @modify(status_code=HTTPStatus.OK)
    def post(self, parsed_body: Body[MobileActivityRecordRequest]) -> SuccessResponse[MobileActivityRecordResponse]:
        user = self.request.user
        recommendations_service = self.get_service(RecommendationService)
        if parsed_body.type == "search":
            try:
                recommendations_service.record_search(user, parsed_body.query, parsed_body.filters)
            except ValueError as exc:
                return self.fail(error=str(exc), status_code=HTTPStatus.BAD_REQUEST)
        elif parsed_body.type == "view":
            try:
                if parsed_body.listing_id is None:
                    return self.fail(error="listing_id_required", status_code=HTTPStatus.BAD_REQUEST)
                recommendations_service.record_view(user, parsed_body.listing_id)
            except Http404, Listing.DoesNotExist:
                return self.fail(error="listing_not_found", status_code=HTTPStatus.NOT_FOUND)
        return self.ok(MobileActivityRecordResponse(recorded=True), status_code=HTTPStatus.OK)
