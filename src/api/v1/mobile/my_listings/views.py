# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _
from dmr import Query
from marketplace.services.listings import ordered_photos, photo_url, photo_variant_url
from property.models import Property

from api.v1.mobile.my_listings.schemas import (
    MobileMyListingItemOutput,
    MobileMyListingsQuery,
    MobileMyListingsResponse,
    MobileMyListingsStatsOutput,
)
from core.api.permissions import BlacklistAwareJWTSyncAuth
from core.api.views import BaseController
from core.constants import ListingStatus, PropertyStatus

_STATUS_DISPLAY = {
    "approved": _("Approved"),
    "pending": _("Pending"),
    "rented": _("Rented"),
    "rejected": _("Rejected"),
    "draft": _("Draft"),
    "archived": _("Archived"),
}


def _safe_float(val: Any, default: float | None = None) -> float | None:
    if val is None:
        return default
    try:
        return float(val)
    except ValueError, TypeError:
        return default


def normalize_property_status(prop: Property) -> str:
    """Normalize property and listing state into standard mobile status."""
    if prop.status == PropertyStatus.RENTED:
        return "rented"

    listing = getattr(prop, "listing", None)
    if listing is not None:
        if listing.status == ListingStatus.PUBLISHED and prop.status == PropertyStatus.VACANT:
            return "approved"
        if listing.status == ListingStatus.PENDING_REVIEW or prop.status == PropertyStatus.PENDING_REVIEW:
            return "pending"
        if listing.status == ListingStatus.REJECTED:
            return "rejected"
        if listing.status == ListingStatus.DRAFT or prop.status == PropertyStatus.DRAFT:
            return "draft"
        if listing.status == ListingStatus.ARCHIVED or prop.status == PropertyStatus.ARCHIVED:
            return "archived"

    if prop.status == PropertyStatus.VACANT:
        return "approved"
    if prop.status == PropertyStatus.PENDING_REVIEW:
        return "pending"
    if prop.status == PropertyStatus.DRAFT:
        return "draft"
    if prop.status == PropertyStatus.ARCHIVED:
        return "archived"

    return "pending"


def calculate_my_listings_stats(properties: list[Property]) -> MobileMyListingsStatsOutput:
    stats = {
        "total_count": len(properties),
        "approved_count": 0,
        "pending_count": 0,
        "rented_count": 0,
        "rejected_count": 0,
        "draft_count": 0,
        "archived_count": 0,
    }
    for prop in properties:
        st = normalize_property_status(prop)
        count_key = f"{st}_count"
        if count_key in stats:
            stats[count_key] += 1
    return MobileMyListingsStatsOutput(**stats)


def serialize_my_listing_item(prop: Property, request) -> dict:
    listing = getattr(prop, "listing", None)
    status_str = normalize_property_status(prop)
    price = None
    currency = "USD"
    rejection_reason = None

    if listing is not None:
        price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
        currency = str(listing.currency or prop.ask_currency or "USD")
        rejection_reason = str(listing.rejection_reason) if listing.rejection_reason else None
    if price is None:
        price = prop.ask_price
        currency = str(prop.ask_currency or "USD")

    photos = ordered_photos(prop)
    cover_photo = photos[0] if photos else None

    views_count = listing.view_activities.filter(deleted_at__isnull=True).count() if listing else 0

    return MobileMyListingItemOutput(
        id=listing.id if listing else prop.id,
        property_id=prop.id,
        title=str(prop.name),
        address=str(prop.address) if prop.address else (str(prop.district.name) if prop.district else ""),
        district=str(prop.district.name) if prop.district else None,
        price=_safe_float(price),
        currency=currency,
        status=status_str,
        status_display=str(_STATUS_DISPLAY.get(status_str, status_str.capitalize())),
        cover_image_url=photo_url(cover_photo, request) if cover_photo else None,
        cover_preview_url=photo_variant_url(cover_photo, "preview_image", request) if cover_photo else None,
        cover_display_url=photo_variant_url(cover_photo, "display_image", request) if cover_photo else None,
        views_count=views_count,
        rooms=prop.rooms,
        area_sqm=prop.area_sqm,
        rejection_reason=rejection_reason,
        created_at=prop.created_at.isoformat() if prop.created_at else None,
    ).model_dump(mode="json")


class MobileMyListingsStatsView(BaseController):
    auth = (BlacklistAwareJWTSyncAuth(),)

    def get(self) -> dict:
        user = self.request.user  # type: ignore[attr-defined]
        properties = list(
            Property.objects.filter(owner=user, deleted_at__isnull=True)
            .select_related("district", "listing")
            .prefetch_related("photos")
            .order_by("-created_at")
        )
        stats = calculate_my_listings_stats(properties)
        return self.ok(stats.model_dump(mode="json"))


class MobileMyListingsListView(BaseController):
    auth = (BlacklistAwareJWTSyncAuth(),)

    def get(self, parsed_query: Query[MobileMyListingsQuery]) -> dict:
        user = self.request.user  # type: ignore[attr-defined]
        properties = list(
            Property.objects.filter(owner=user, deleted_at__isnull=True)
            .select_related("district", "listing")
            .prefetch_related("photos", "listing__view_activities")
            .order_by("-created_at")
        )
        stats = calculate_my_listings_stats(properties)

        query_status = (parsed_query.status or "all").lower().strip()
        if query_status and query_status != "all":
            filtered_properties = [p for p in properties if normalize_property_status(p) == query_status]
        else:
            filtered_properties = properties

        listings_data = [serialize_my_listing_item(p, self.request) for p in filtered_properties]

        response = MobileMyListingsResponse(
            stats=stats,
            listings=listings_data,  # type: ignore[arg-type]
        )
        return self.ok(response.model_dump(mode="json"))
