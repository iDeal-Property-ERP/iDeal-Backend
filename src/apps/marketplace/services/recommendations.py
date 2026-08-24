from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from account.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from marketplace.models import FavoriteListing, Listing, ListingViewActivity, RecentSearchActivity
from marketplace.services.listings import ListingFilters, apply_listing_filters, published_listings_queryset

MAX_RETAINED_SEARCHES = 20
MAX_RETAINED_VIEWS = 100
MAX_RECOMMENDED_ITEMS = 6
MAX_FAVORITES_SEEDS = 20

_ALLOWED_FILTER_KEYS = {
    "district_id",
    "property_type",
    "price_min",
    "price_max",
    "rooms_min",
    "rooms_max",
    "verified",
    "furnishing",
    "tariff",
}


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


def normalize_search_payload(query: str | None, filters: dict[str, Any] | None) -> tuple[str, dict[str, Any], str]:
    normalized_query = (query or "").strip()
    normalized_filters: dict[str, Any] = {}

    if filters and isinstance(filters, dict):
        for key, val in filters.items():
            if key in _ALLOWED_FILTER_KEYS and val is not None:
                if isinstance(val, str):
                    val_str = val.strip()
                    if val_str:
                        normalized_filters[key] = val_str
                elif isinstance(val, (int, float, bool)):
                    normalized_filters[key] = val

    if not normalized_query and not normalized_filters:
        raise ValueError("Search activity must have a query or at least one substantive filter.")

    canonical_repr = json.dumps(
        {
            "query": normalized_query.lower(),
            "filters": {k: normalized_filters[k] for k in sorted(normalized_filters)},
        },
        sort_keys=True,
    )
    fingerprint = hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()
    return normalized_query, normalized_filters, fingerprint


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


class RecommendationService:
    """Activity-backed discovery recommendations with injectable persistence and clock."""

    def __init__(
        self,
        *,
        user_model=User,
        listing_model=Listing,
        search_activity_model=RecentSearchActivity,
        view_activity_model=ListingViewActivity,
        favorite_model=FavoriteListing,
        now=timezone.now,
    ):
        self.user_model = user_model
        self.listing_model = listing_model
        self.search_activity_model = search_activity_model
        self.view_activity_model = view_activity_model
        self.favorite_model = favorite_model
        self.now = now

    @transaction.atomic
    def record_search(self, user: User, query: str | None, filters: dict[str, Any] | None) -> RecentSearchActivity:
        normalized_query, normalized_filters, fingerprint = normalize_search_payload(query, filters)

        # Lock user record to serialize activity writes per user
        self.user_model.objects.select_for_update().get(id=user.id)

        activity = (
            self.search_activity_model.global_objects.select_for_update()
            .filter(user=user, fingerprint=fingerprint)
            .order_by("-updated_at", "-id")
            .first()
        )

        now = self.now()
        if activity is None:
            activity = self.search_activity_model.objects.create(
                user=user,
                query=normalized_query,
                filters=normalized_filters,
                fingerprint=fingerprint,
            )
        else:
            activity.query = normalized_query
            activity.filters = normalized_filters
            activity.deleted_at = None
            activity.restored_at = now
            activity.updated_at = now
            activity.save(update_fields=["query", "filters", "deleted_at", "restored_at", "updated_at"])

        # Prune beyond 20 searches
        all_ids = list(
            self.search_activity_model.objects.filter(user=user)
            .order_by("-updated_at", "-id")
            .values_list("id", flat=True)
        )
        if len(all_ids) > MAX_RETAINED_SEARCHES:
            self.search_activity_model.objects.filter(id__in=all_ids[MAX_RETAINED_SEARCHES:]).hard_delete()

        return activity

    @transaction.atomic
    def record_view(self, user: User, listing_id: int) -> ListingViewActivity:
        listing = get_object_or_404(self.listing_model, pk=listing_id)

        # Lock user record to serialize activity writes per user
        self.user_model.objects.select_for_update().get(id=user.id)

        activity = (
            self.view_activity_model.global_objects.select_for_update()
            .filter(user=user, listing=listing)
            .order_by("-updated_at", "-id")
            .first()
        )

        now = self.now()
        if activity is None:
            activity = self.view_activity_model.objects.create(user=user, listing=listing)
        else:
            activity.deleted_at = None
            activity.restored_at = now
            activity.updated_at = now
            activity.save(update_fields=["deleted_at", "restored_at", "updated_at"])

        # Prune beyond 100 views
        all_ids = list(
            self.view_activity_model.objects.filter(user=user)
            .order_by("-updated_at", "-id")
            .values_list("id", flat=True)
        )
        if len(all_ids) > MAX_RETAINED_VIEWS:
            self.view_activity_model.objects.filter(id__in=all_ids[MAX_RETAINED_VIEWS:]).hard_delete()

        return activity

    def get_recommendations(self, user: User, *, limit: int = MAX_RECOMMENDED_ITEMS) -> list[Listing]:
        searches = list(
            self.search_activity_model.objects.filter(user=user).order_by("-updated_at", "-id")[:MAX_RETAINED_SEARCHES]
        )
        views = list(
            self.view_activity_model.objects.filter(user=user)
            .select_related("listing__property__district")
            .prefetch_related("listing__property__photos", "listing__property__amenities")
            .order_by("-updated_at", "-id")[:MAX_RETAINED_VIEWS]
        )
        favorites = list(
            self.favorite_model.objects.filter(user=user)
            .select_related("listing__property__district")
            .prefetch_related("listing__property__photos", "listing__property__amenities")
            .order_by("-created_at", "-id")[:MAX_FAVORITES_SEEDS]
        )

        if not searches and not views and not favorites:
            return []

        # Exclude all retained views and active favorites
        excluded_view_ids = set(self.view_activity_model.objects.filter(user=user).values_list("listing_id", flat=True))
        excluded_fav_ids = set(self.favorite_model.objects.filter(user=user).values_list("listing_id", flat=True))
        excluded_ids = excluded_view_ids | excluded_fav_ids

        candidate_qs = apply_listing_filters(
            published_listings_queryset(), ListingFilters(), include_future_managed=True
        ).exclude(id__in=excluded_ids)

        candidates = list(candidate_qs)
        if not candidates:
            return []

        scored_candidates: list[tuple[float, float, float, int, Listing]] = []

        for cand in candidates:
            cand_prop = cand.property
            cand_monthly = cand.monthly_price if cand.monthly_price is not None else cand.listed_price
            cand_price = _safe_float(cand_monthly)
            cand_title = (cand_prop.name or "").lower()
            cand_address = (cand_prop.address or "").lower()
            cand_district_name = (cand_prop.district.name or "").lower() if cand_prop.district else ""
            cand_district_id = cand_prop.district_id
            cand_property_type = cand_prop.property_type
            cand_rooms = cand_prop.rooms
            cand_area = cand_prop.area_sqm
            cand_verified = cand_prop.is_verified
            cand_furnishing = cand_prop.furnishing
            cand_tariff = cand_prop.tariff
            cand_tokens = _tokenize(f"{cand_prop.name or ''} {cand_prop.address or ''}")
            cand_prop_score = _safe_float(cand_prop.score, 0.0) or 0.0
            cand_created_at_ts = cand.created_at.timestamp() if cand.created_at else 0.0

            total_score = 0.0

            # 1. Score against searches (source weight = 2.0)
            for rank, search in enumerate(searches):
                recency = 1.0 / (rank + 1.0)
                points = 0
                q = (search.query or "").strip().lower()
                if q and (q in cand_title or q in cand_address or q in cand_district_name):
                    points += 5

                f = search.filters or {}
                if f.get("district_id") is not None and f.get("district_id") == cand_district_id:
                    points += 5
                if f.get("property_type") and f.get("property_type") == cand_property_type:
                    points += 4
                if (f.get("price_min") is not None or f.get("price_max") is not None) and cand_price is not None:
                    p_min = _safe_float(f.get("price_min"))
                    p_max = _safe_float(f.get("price_max"))
                    in_min = p_min is None or cand_price >= p_min
                    in_max = p_max is None or cand_price <= p_max
                    if in_min and in_max:
                        points += 3
                if (f.get("rooms_min") is not None or f.get("rooms_max") is not None) and cand_rooms is not None:
                    r_min = _safe_int(f.get("rooms_min"))
                    r_max = _safe_int(f.get("rooms_max"))
                    in_min = r_min is None or cand_rooms >= r_min
                    in_max = r_max is None or cand_rooms <= r_max
                    if in_min and in_max:
                        points += 3
                if f.get("verified") is not None and bool(f.get("verified")) == cand_verified:
                    points += 1
                if f.get("furnishing") and f.get("furnishing") == cand_furnishing:
                    points += 1
                if f.get("tariff") and f.get("tariff") == cand_tariff:
                    points += 1

                if points > 0:
                    total_score += points * 2.0 * recency

            # 2. Score against views (source weight = 1.0)
            for rank, view_act in enumerate(views):
                seed_listing = view_act.listing
                if not seed_listing:
                    continue
                recency = 1.0 / (rank + 1.0)
                points = self._score_listing_seed(
                    cand_prop,
                    cand_price,
                    cand_rooms,
                    cand_area,
                    cand_furnishing,
                    cand_tariff,
                    cand_tokens,
                    seed_listing,
                )
                if points > 0:
                    total_score += points * 1.0 * recency

            # 3. Score against favorites (source weight = 3.0)
            for rank, fav in enumerate(favorites):
                seed_listing = fav.listing
                if not seed_listing:
                    continue
                recency = 1.0 / (rank + 1.0)
                points = self._score_listing_seed(
                    cand_prop,
                    cand_price,
                    cand_rooms,
                    cand_area,
                    cand_furnishing,
                    cand_tariff,
                    cand_tokens,
                    seed_listing,
                )
                if points > 0:
                    total_score += points * 3.0 * recency

            if total_score > 0:
                scored_candidates.append((total_score, cand_prop_score, cand_created_at_ts, cand.id, cand))

        # Sort by total score desc, property score desc, created_at desc, id desc
        scored_candidates.sort(key=lambda x: (-x[0], -x[1], -x[2], -x[3]))

        return [item[4] for item in scored_candidates[:limit]]

    def _score_listing_seed(
        self,
        cand_prop,
        cand_price: float | None,
        cand_rooms: int | None,
        cand_area: int | None,
        cand_furnishing: str | None,
        cand_tariff: str | None,
        cand_tokens: set[str],
        seed_listing: Listing,
    ) -> int:
        seed_prop = seed_listing.property
        seed_monthly = (
            seed_listing.monthly_price if seed_listing.monthly_price is not None else seed_listing.listed_price
        )
        seed_price = _safe_float(seed_monthly)
        seed_area = _safe_float(seed_prop.area_sqm)

        points = 0

        # district +5
        if cand_prop.district_id is not None and cand_prop.district_id == seed_prop.district_id:
            points += 5

        # property type +4
        if cand_prop.property_type and cand_prop.property_type == seed_prop.property_type:
            points += 4

        # rooms +3
        if cand_rooms is not None and cand_rooms == seed_prop.rooms:
            points += 3

        # price within 15/30/50 percent +3/+2/+1
        if cand_price is not None and seed_price is not None and seed_price > 0:
            diff_ratio = abs(cand_price - seed_price) / seed_price
            if diff_ratio <= 0.15:
                points += 3
            elif diff_ratio <= 0.30:
                points += 2
            elif diff_ratio <= 0.50:
                points += 1

        # token overlap +2
        seed_tokens = _tokenize(f"{seed_prop.name or ''} {seed_prop.address or ''}")
        if cand_tokens & seed_tokens:
            points += 2

        # area within 20 percent +1
        if cand_area is not None and seed_area is not None and seed_area > 0:
            area_diff = abs(cand_area - seed_area) / seed_area
            if area_diff <= 0.20:
                points += 1

        # furnishing +1
        if cand_furnishing and cand_furnishing == seed_prop.furnishing:
            points += 1

        # tariff +1
        if cand_tariff and cand_tariff == seed_prop.tariff:
            points += 1

        return points
