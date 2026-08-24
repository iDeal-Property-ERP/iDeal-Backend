from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from marketplace.models import FavoriteListing, Listing
from marketplace.services.listings import ListingDiscoveryService, ListingFilters, published_listings_queryset


class FavoriteListingService:
    """Favorite lifecycle service; models are injectable for isolated unit tests."""

    def __init__(self, *, favorite_model=FavoriteListing, listing_filter_service=None):
        self.favorite_model = favorite_model
        self.listing_filter_service = listing_filter_service

    def favorite_listing_ids(self, user):
        return self.favorite_model.objects.filter(user=user).values("listing_id")

    def favorite_ids_for_listings(self, user, listing_ids: list[int]) -> set[int]:
        if user is None or not listing_ids:
            return set()
        return set(
            self.favorite_model.objects.filter(user=user, listing_id__in=listing_ids).values_list(
                "listing_id", flat=True
            )
        )

    def eligible_listing(self, listing_id: int) -> Listing | None:
        discovery = self.listing_filter_service or ListingDiscoveryService()
        return (
            discovery.filter(
                published_listings_queryset().filter(pk=listing_id),
                ListingFilters(),
                include_future_managed=True,
            )
            .select_related("property__district")
            .prefetch_related("property__photos", "property__amenities")
            .first()
        )

    @transaction.atomic
    def favorite(self, user, listing: Listing) -> FavoriteListing:
        favorite = (
            self.favorite_model.global_objects.select_for_update()
            .filter(user=user, listing=listing)
            .order_by("-created_at", "-id")
            .first()
        )
        if favorite is None:
            try:
                with transaction.atomic():
                    return self.favorite_model.objects.create(user=user, listing=listing)
            except IntegrityError:
                # Another request may have inserted the active row after the
                # initial lookup. The savepoint keeps this transaction usable
                # while the conditional unique constraint serializes the
                # competing insert.
                favorite = (
                    self.favorite_model.global_objects.select_for_update()
                    .filter(user=user, listing=listing, deleted_at__isnull=True)
                    .order_by("-created_at", "-id")
                    .first()
                )
                if favorite is None:
                    raise
        if favorite.deleted_at is not None:
            favorite.deleted_at = None
            favorite.restored_at = timezone.now()
            favorite.transaction_id = None
            favorite.save(update_fields=["deleted_at", "restored_at", "transaction_id", "updated_at"])
        return favorite

    def unfavorite(self, user, listing_id: int) -> bool:
        favorite = self.favorite_model.objects.filter(user=user, listing_id=listing_id).first()
        if favorite is None:
            return False
        favorite.delete()
        return True

    def paged_favorites_queryset(self, user, filters: ListingFilters | None = None, *, sort: str = "recent"):
        filters = filters or ListingFilters()
        discovery = self.listing_filter_service or ListingDiscoveryService()
        eligible_listing_ids = discovery.filter(
            published_listings_queryset().filter(id__in=Subquery(self.favorite_listing_ids(user))),
            filters,
            include_future_managed=True,
        ).values("id")
        queryset = (
            self.favorite_model.objects.filter(user=user, listing_id__in=Subquery(eligible_listing_ids))
            .select_related("listing__property__district")
            .prefetch_related("listing__property__photos", "listing__property__amenities")
        )
        if sort in {"price_asc", "price_desc"}:
            queryset = queryset.annotate(_price=Coalesce("listing__monthly_price", "listing__listed_price")).order_by(
                ("-" if sort == "price_desc" else "") + "_price", "-created_at", "-id"
            )
        else:
            queryset = queryset.order_by("-created_at", "-id")
        return queryset
