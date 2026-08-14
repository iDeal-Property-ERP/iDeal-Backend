from http import HTTPStatus

import pydantic
from django.core.paginator import Paginator
from dmr import Path, Query, modify
from dmr.pagination import Page, Paginated
from marketplace.services.favorites import FavoriteListingService

from api.v1.mobile.home.views import serialize_mobile_listing_card
from core.api.views import BaseController


class FavoriteListingPath(pydantic.BaseModel):
    listing_id: int


class FavoriteListingQuery(pydantic.BaseModel):
    page: int = 1
    per_page: int = 20


class MobileFavoriteListView(BaseController):
    def get(self, parsed_query: Query[FavoriteListingQuery]) -> dict:
        queryset = FavoriteListingService.paged_favorites_queryset(self.request.user)
        paginator = Paginator(queryset, parsed_query.per_page)
        django_page = paginator.get_page(parsed_query.page)
        favorites = list(django_page.object_list)
        paginated = Paginated(
            count=paginator.count,
            num_pages=paginator.num_pages,
            per_page=paginator.per_page,
            page=Page(
                number=django_page.number,
                object_list=[
                    serialize_mobile_listing_card(favorite.listing, self.request, favorite_ids={favorite.listing_id})
                    for favorite in favorites
                ],
            ),
        )
        return self.ok(paginated)


class MobileFavoriteDetailView(BaseController):
    @modify(status_code=HTTPStatus.OK)
    def put(self, parsed_path: Path[FavoriteListingPath]) -> dict:
        listing = FavoriteListingService.eligible_listing(parsed_path.listing_id)
        if listing is None:
            return self.fail(error="listing_unavailable", status_code=HTTPStatus.NOT_FOUND)
        FavoriteListingService.favorite(self.request.user, listing)
        return self.ok(
            serialize_mobile_listing_card(listing, self.request, favorite_ids={listing.id}),
            status_code=HTTPStatus.OK,
        )

    @modify(status_code=HTTPStatus.OK)
    def delete(self, parsed_path: Path[FavoriteListingPath]) -> dict:
        FavoriteListingService.unfavorite(self.request.user, parsed_path.listing_id)
        return self.ok({"id": parsed_path.listing_id, "is_favorite": False}, status_code=HTTPStatus.OK)
