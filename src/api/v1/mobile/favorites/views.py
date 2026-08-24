from http import HTTPStatus
from typing import Literal

import pydantic
from dmr import Path, Query, modify
from marketplace.services.favorites import FavoriteListingService
from marketplace.services.listings import ListingFilters

from api.v1.mobile.home.schemas import MobileHomeFeedQuery, MobileListingCard
from core.api.schemas import Pagination, SuccessResponse
from core.api.views import BaseController
from core.utils.pagination import build_paginated_response_from_queryset


class FavoriteListingPath(pydantic.BaseModel):
    listing_id: int


class FavoriteListingQuery(MobileHomeFeedQuery):
    sort: Literal["recent", "price_asc", "price_desc"] = "recent"


class MobileFavoriteListView(BaseController):
    def get(self, parsed_query: Query[FavoriteListingQuery]) -> SuccessResponse[Pagination[MobileListingCard]]:
        filters = ListingFilters(**parsed_query.model_dump(exclude={"sort"}))
        favorites_service = self.get_service(FavoriteListingService)
        queryset = favorites_service.paged_favorites_queryset(self.request.user, filters, sort=parsed_query.sort)
        paginated = build_paginated_response_from_queryset(
            queryset,
            parsed_query.page,
            parsed_query.per_page,
            lambda favorite: MobileListingCard.from_listing(
                favorite.listing, request=self.request, favorite_ids={favorite.listing_id}
            ),
        )
        return self.ok(paginated)


class MobileFavoriteDetailView(BaseController):
    @modify(status_code=HTTPStatus.OK)
    def put(self, parsed_path: Path[FavoriteListingPath]) -> SuccessResponse[MobileListingCard]:
        favorites_service = self.get_service(FavoriteListingService)
        listing = favorites_service.eligible_listing(parsed_path.listing_id)
        if listing is None:
            return self.fail(error="listing_unavailable", status_code=HTTPStatus.NOT_FOUND)
        favorites_service.favorite(self.request.user, listing)
        return self.ok(
            MobileListingCard.from_listing(listing, request=self.request, favorite_ids={listing.id}),
            status_code=HTTPStatus.OK,
        )

    @modify(status_code=HTTPStatus.OK)
    def delete(self, parsed_path: Path[FavoriteListingPath]) -> SuccessResponse[dict]:
        self.get_service(FavoriteListingService).unfavorite(self.request.user, parsed_path.listing_id)
        return self.ok({"id": parsed_path.listing_id, "is_favorite": False}, status_code=HTTPStatus.OK)
