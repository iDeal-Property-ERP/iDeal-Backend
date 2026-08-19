from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from marketplace.models import FavoriteListing, Listing
from marketplace.services.listings import ListingFilters, apply_listing_filters, published_listings_queryset


class FavoriteListingService:
    @staticmethod
    def favorite_listing_ids(user):
        return FavoriteListing.objects.filter(user=user).values("listing_id")

    @staticmethod
    def favorite_ids_for_listings(user, listing_ids: list[int]) -> set[int]:
        if user is None or not listing_ids:
            return set()
        return set(
            FavoriteListing.objects.filter(user=user, listing_id__in=listing_ids).values_list("listing_id", flat=True)
        )

    @staticmethod
    def eligible_listing(listing_id: int) -> Listing | None:
        return (
            apply_listing_filters(
                published_listings_queryset().filter(pk=listing_id),
                ListingFilters(),
                include_future_managed=True,
            )
            .select_related("property__district")
            .prefetch_related("property__photos", "property__amenities")
            .first()
        )

    @staticmethod
    @transaction.atomic
    def favorite(user, listing: Listing) -> FavoriteListing:
        favorite = (
            FavoriteListing.global_objects.select_for_update()
            .filter(user=user, listing=listing)
            .order_by("-created_at", "-id")
            .first()
        )
        if favorite is None:
            try:
                with transaction.atomic():
                    return FavoriteListing.objects.create(user=user, listing=listing)
            except IntegrityError:
                # Another request may have inserted the active row after the
                # initial lookup. The savepoint keeps this transaction usable
                # while the conditional unique constraint serializes the
                # competing insert.
                favorite = (
                    FavoriteListing.global_objects.select_for_update()
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

    @staticmethod
    def unfavorite(user, listing_id: int) -> bool:
        favorite = FavoriteListing.objects.filter(user=user, listing_id=listing_id).first()
        if favorite is None:
            return False
        favorite.delete()
        return True

    @staticmethod
    def paged_favorites_queryset(user, filters: ListingFilters | None = None, *, sort: str = "recent"):
        filters = filters or ListingFilters()
        eligible_listing_ids = apply_listing_filters(
            published_listings_queryset().filter(id__in=Subquery(FavoriteListingService.favorite_listing_ids(user))),
            filters,
            include_future_managed=True,
        ).values("id")
        queryset = (
            FavoriteListing.objects.filter(user=user, listing_id__in=Subquery(eligible_listing_ids))
            .select_related("listing__property__district")
            .prefetch_related("listing__property__photos", "listing__property__amenities")
        )
        if sort in {"price_asc", "price_desc"}:
            queryset = queryset.annotate(
                _price=Coalesce("listing__monthly_price", "listing__listed_price")
            ).order_by(("-" if sort == "price_desc" else "") + "_price", "-created_at", "-id")
        else:
            queryset = queryset.order_by("-created_at", "-id")
        return queryset
