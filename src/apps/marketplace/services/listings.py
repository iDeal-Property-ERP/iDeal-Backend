from __future__ import annotations

import datetime

import pydantic
from contract.models import Lease
from django.db.models import Q
from django.db.models.functions import Coalesce
from marketplace.models import Booking, Listing

from core.api.filters import PydanticFilterSet
from core.constants import (
    BookingStatus,
    LeaseStatus,
    ListingStatus,
    OwnerAgreementStatus,
    PaymentCheckoutStatus,
    PropertyEngagementType,
    PropertyStatus,
)


class ListingFilters(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="ignore")
    page: int = 1
    per_page: int = 20
    district_id: int | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    flexibility_days: int | None = None
    price_min: float | None = None
    price_max: float | None = None
    rooms: int | None = None
    rooms_min: int | None = None
    rooms_max: int | None = None
    area_min: int | None = None
    area_max: int | None = None
    verified: bool | None = None
    furnishing: str | None = None
    tariff: str | None = None
    property_type: str | None = None
    amenities: str | None = None  # csv of amenity slugs (AND-match)
    sort: str | None = None  # newest | price_asc | price_desc | score_desc | rating_desc
    q: str | None = None
    bbox: str | None = None  # "minLon,minLat,maxLon,maxLat" for "search this area"

    @pydantic.model_validator(mode="after")
    def validate_dates(self):
        if bool(self.start_date) != bool(self.end_date):
            raise ValueError("Both start_date and end_date must be provided.")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date.")
        if self.flexibility_days is not None and self.flexibility_days < 0:
            raise ValueError("flexibility_days cannot be negative.")
        return self


def published_listings_queryset():
    return (
        Listing.objects.select_related("property__district")
        .prefetch_related("property__photos", "property__amenities")
        .filter(status=ListingStatus.PUBLISHED)
        .annotate(_price=Coalesce("monthly_price", "listed_price"))
    )


class ListingFilterSet(PydanticFilterSet[ListingFilters]):
    """Filtering, search and ordering for listing discovery querysets only."""

    class Meta:
        model = Listing
        fields: list[str] = []

    def filter_queryset(self, queryset):
        q = self.query
        qs = queryset

        if q.district_id is not None:
            qs = qs.filter(property__district_id=q.district_id)
        if q.price_min is not None:
            qs = qs.filter(_price__gte=q.price_min)
        if q.price_max is not None:
            qs = qs.filter(_price__lte=q.price_max)
        if q.rooms is not None:
            qs = qs.filter(property__rooms=q.rooms)
        if q.rooms_min is not None:
            qs = qs.filter(property__rooms__gte=q.rooms_min)
        if q.rooms_max is not None:
            qs = qs.filter(property__rooms__lte=q.rooms_max)
        if q.area_min is not None:
            qs = qs.filter(property__area_sqm__gte=q.area_min)
        if q.area_max is not None:
            qs = qs.filter(property__area_sqm__lte=q.area_max)
        if q.verified is not None:
            qs = qs.filter(property__is_verified=q.verified)
        if q.furnishing:
            qs = qs.filter(property__furnishing=q.furnishing)
        if q.tariff:
            qs = qs.filter(property__tariff=q.tariff)
        if q.property_type:
            qs = qs.filter(property__property_type=q.property_type)
        if q.amenities:
            for slug in (value.strip() for value in q.amenities.split(",")):
                if slug:
                    qs = qs.filter(property__amenities__slug=slug)
            qs = qs.distinct()
        if q.q:
            qs = qs.filter(
                Q(property__name__icontains=q.q)
                | Q(property__address__icontains=q.q)
                | Q(property__district__name__icontains=q.q)
            )
        if q.bbox:
            # Legacy callers do not use the bounded mobile map query.  Keep
            # their historical ignore-on-malformed policy until their v1 slice
            # is migrated, while MobileHomeMapQuery now rejects it at parsing.
            try:
                min_lon, min_lat, max_lon, max_lat = (float(v) for v in q.bbox.split(","))
            except TypeError, ValueError:
                pass
            else:
                qs = qs.filter(
                    property__map_lat__gte=min_lat,
                    property__map_lat__lte=max_lat,
                    property__map_lon__gte=min_lon,
                    property__map_lon__lte=max_lon,
                )

        if q.sort == "price_asc":
            return qs.order_by("_price", "-created_at", "-id")
        if q.sort == "price_desc":
            return qs.order_by("-_price", "-created_at", "-id")
        if q.sort in ("score_desc", "rating_desc"):
            return qs.order_by("-property__score", "-is_featured", "-created_at", "-id")
        return qs.order_by("-is_featured", "-created_at", "-id")


class ListingDiscoveryService:
    """Prepares visible/available listing querysets before a FilterSet runs."""

    def __init__(self, *, booking_service_factory=None):
        self.booking_service_factory = booking_service_factory

    def filter(self, queryset, filters: ListingFilters, *, request=None, include_future_managed: bool = False):
        queryset = self.visible_queryset(queryset, filters, include_future_managed=include_future_managed)
        return ListingFilterSet(query=filters, request=request, queryset=queryset).apply()

    def visible_queryset(self, qs, filters: ListingFilters, *, include_future_managed: bool = False):
        """Apply availability and visibility; never apply query filters here."""
        q = filters
        if q.start_date and q.end_date:
            flex = q.flexibility_days if q.flexibility_days is not None else 3
            latest_acceptable_start = q.start_date + datetime.timedelta(days=flex)
            earliest_acceptable_end = q.end_date - datetime.timedelta(days=flex)

            overlapping_leases = Lease.objects.filter(
                status__in=[LeaseStatus.PENDING_SIGNATURE, LeaseStatus.SCHEDULED, LeaseStatus.ACTIVE],
                start_date__lte=earliest_acceptable_end,
                end_date__gte=latest_acceptable_start,
            )
            overlapping_bookings = Booking.objects.filter(
                Q(status=BookingStatus.CONFIRMED)
                | Q(
                    status=BookingStatus.PAYMENT_PENDING,
                    payment_checkout__status=PaymentCheckoutStatus.PENDING,
                    payment_checkout__expires_at__gt=datetime.datetime.now(datetime.UTC),
                ),
                requested_start_date__lte=earliest_acceptable_end,
                requested_end_date__gte=latest_acceptable_start,
            )
            return (
                qs.filter(
                    property__owner_agreements__status=OwnerAgreementStatus.ACTIVE,
                    property__owner_agreements__start_date__lte=latest_acceptable_start,
                    property__owner_agreements__end_date__gte=earliest_acceptable_end,
                )
                .exclude(property__leases__in=overlapping_leases)
                .exclude(property__bookings__in=overlapping_bookings)
                .distinct()
            )

        future_managed = Q(pk__in=[])
        if include_future_managed:
            from marketplace.services.booking import BookingService

            booking_service = self.booking_service_factory() if self.booking_service_factory else BookingService()
            if booking_service.enabled_providers():
                future_managed = Q(
                    property__engagement_type=PropertyEngagementType.MANAGED,
                    property__is_verified=True,
                    property__owner_agreements__status=OwnerAgreementStatus.ACTIVE,
                    property__owner_agreements__end_date__gte=datetime.date.today(),
                )
        return qs.filter(Q(property__status=PropertyStatus.VACANT) | future_managed).distinct()


def apply_listing_filters(qs, filters: ListingFilters, *, include_future_managed: bool = False):
    """Compatibility façade for callers not migrated to ``ListingDiscoveryService``."""
    return ListingDiscoveryService().filter(qs, filters, include_future_managed=include_future_managed)


def photo_url(photo, request):
    """Build an absolute URL for a property photo, falling back to the relative media URL."""
    url = photo.image.url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


def photo_variant_url(photo, field_name, request):
    """Build an absolute URL for an optional photo variant, or None for legacy rows."""
    variant = getattr(photo, field_name, None)
    if not variant or not getattr(variant, "name", None):
        return None
    url = variant.url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


def ordered_photos(prop):
    """Photos ordered primary-first, then by sort_order (uses prefetched cache when available)."""
    return sorted(prop.photos.all(), key=lambda p: (not p.is_primary, p.sort_order))
