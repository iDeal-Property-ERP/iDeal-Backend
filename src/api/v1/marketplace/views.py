from __future__ import annotations

import pydantic
from django.db import models
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from marketplace.models import ContactInquiry, FaqItem, Listing, ViewingRequest
from property.models import District, Property

from api.v1.marketplace.schemas import (
    ContactInquiryCreateInput,
    ViewingRequestCreateInput,
)
from core.api.views import BaseController, DetailPath, GenericController, ListAPIView, RetrieveAPIView
from core.constants import ListingStatus, PropertyStatus
from core.utils.pagination import build_paginated_response

# Static verification checklist shown on every verified listing's detail page.
VERIFICATION_CHECKLIST = [
    {"key": "ownership", "label": _("Official ownership check")},
    {"key": "team", "label": _("Verified by iDeal team")},
    {"key": "contract", "label": _("In-app contract & payments")},
    {"key": "managed", "label": _("Managed end-to-end")},
]
RESPONSE_TIME = _("Usually responds within 1 hour")


def _photo_url(photo, request):
    """Build an absolute URL for a property photo, falling back to the relative media URL."""
    url = photo.image.url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


def _ordered_photos(prop):
    """Photos ordered primary-first, then by sort_order (uses prefetched cache when available)."""
    return sorted(prop.photos.all(), key=lambda p: (not p.is_primary, p.sort_order))


def _amenities_brief(prop):
    return [{"slug": a.slug, "name": a.name, "icon": a.icon} for a in prop.amenities.all() if a.is_active]


def _build_property_brief(prop, request=None):
    photos = _ordered_photos(prop)
    image_urls = [_photo_url(p, request) for p in photos[:5]]
    return {
        "id": prop.id,
        "name": prop.name,
        "address": prop.address,
        "district_id": prop.district_id,
        "district_name": prop.district.name if prop.district else None,
        "property_type": prop.property_type,
        "rooms": prop.rooms,
        "bathrooms": prop.bathrooms,
        "area_sqm": prop.area_sqm,
        "floor": prop.floor,
        "total_floors": prop.total_floors,
        "furnishing": prop.furnishing,
        "status": prop.status,
        "is_verified": prop.is_verified,
        "score": str(prop.score),
        "review_count": prop.review_count,
        "map_lat": str(prop.map_lat) if prop.map_lat is not None else None,
        "map_lon": str(prop.map_lon) if prop.map_lon is not None else None,
        "tariff": prop.tariff,
        "ask_price": str(prop.ask_price),
        "ask_currency": prop.ask_currency,
        "amenities": _amenities_brief(prop),
        "image_url": image_urls[0] if image_urls else None,
        "image_urls": image_urls,
    }


def _build_listing_output(listing, request=None):
    monthly_price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
    return {
        "id": listing.id,
        "property": _build_property_brief(listing.property, request),
        "property_id": listing.property_id,
        "owner_agreement_id": listing.owner_agreement_id,
        "status": listing.status,
        "is_active": listing.is_active,
        "is_featured": listing.is_featured,
        "description": listing.description,
        "listed_price": str(listing.listed_price) if listing.listed_price is not None else None,
        "monthly_price": str(monthly_price) if monthly_price is not None else None,
        "deposit_amount": str(listing.deposit_amount) if listing.deposit_amount is not None else None,
        "currency": listing.currency,
        "created_at": listing.created_at.isoformat(),
        "updated_at": listing.updated_at.isoformat(),
    }


def _build_listing_detail(listing, request=None):
    """Enriched detail payload: full photo gallery, labelled amenities, specs, price card
    and a static verification block."""
    prop = listing.property
    photos = _ordered_photos(prop)
    monthly_price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
    deposit = listing.deposit_amount if listing.deposit_amount is not None else prop.deposit_amount
    output = _build_listing_output(listing, request)
    output.update(
        {
            "photos": [
                {
                    "id": p.id,
                    "image_url": _photo_url(p, request),
                    "caption": p.caption or None,
                    "is_primary": p.is_primary,
                    "sort_order": p.sort_order,
                }
                for p in photos
            ],
            "specs": {
                "property_type": prop.property_type,
                "rooms": prop.rooms,
                "bathrooms": prop.bathrooms,
                "area_sqm": prop.area_sqm,
                "floor": prop.floor,
                "total_floors": prop.total_floors,
                "furnishing": prop.furnishing,
                "tariff": prop.tariff,
            },
            "price_card": {
                "monthly_price": str(monthly_price) if monthly_price is not None else None,
                "deposit_amount": str(deposit) if deposit is not None else None,
                "currency": listing.currency or prop.ask_currency,
                "minimum_stay": listing.minimum_stay,
                "price_includes": listing.price_includes or [],
                "response_time": str(RESPONSE_TIME),
            },
            "verification": {
                "is_verified": prop.is_verified,
                "checklist": [{"key": item["key"], "label": str(item["label"])} for item in VERIFICATION_CHECKLIST],
            },
        }
    )
    return output


class ListingFilterQuery(pydantic.BaseModel):
    page: int = 1
    per_page: int = 20
    district_id: int | None = None
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
    sort: str | None = None  # newest | price_asc | price_desc
    q: str | None = None
    bbox: str | None = None  # "minLon,minLat,maxLon,maxLat" for "search this area"


class ListingListView(ListAPIView):
    model = Listing
    auth = ()

    def get_queryset(self):
        return (
            Listing.objects.select_related("property__district")
            .prefetch_related("property__photos", "property__amenities")
            .filter(is_active=True, status=ListingStatus.PUBLISHED, property__status=PropertyStatus.VACANT)
        )

    def _price_field(self):
        # Prefer monthly_price, fall back to legacy listed_price for older rows.
        return models.functions.Coalesce("monthly_price", "listed_price")

    def get(self, parsed_query: Query[ListingFilterQuery]) -> dict:
        qs = self.get_queryset().annotate(_price=self._price_field())
        q = parsed_query

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
            slugs = [s.strip() for s in q.amenities.split(",") if s.strip()]
            for slug in slugs:  # AND-match: every requested amenity must be present
                qs = qs.filter(property__amenities__slug=slug)
            qs = qs.distinct()
        if q.q:
            qs = qs.filter(
                models.Q(property__name__icontains=q.q)
                | models.Q(property__address__icontains=q.q)
                | models.Q(property__district__name__icontains=q.q)
            )
        if q.bbox:
            try:
                min_lon, min_lat, max_lon, max_lat = (float(v) for v in q.bbox.split(","))
                qs = qs.filter(
                    property__map_lat__gte=min_lat,
                    property__map_lat__lte=max_lat,
                    property__map_lon__gte=min_lon,
                    property__map_lon__lte=max_lon,
                )
            except ValueError, TypeError:
                pass

        if q.sort == "price_asc":
            qs = qs.order_by("_price", "-created_at")
        elif q.sort == "price_desc":
            qs = qs.order_by("-_price", "-created_at")
        else:  # newest (default) — featured first
            qs = qs.order_by("-is_featured", "-created_at")

        items = [_build_listing_output(obj, self.request) for obj in qs]
        paginated = build_paginated_response(items, q.page, q.per_page)
        return self.ok(paginated)


class ListingDetailView(RetrieveAPIView):
    model = Listing
    auth = ()

    def get_queryset(self):
        return (
            Listing.objects.select_related("property__district")
            .prefetch_related("property__photos", "property__amenities")
            .all()
        )

    def get(self, parsed_path: Path[DetailPath]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        return self.ok(_build_listing_detail(instance, self.request))


class ListingMapView(GenericController):
    model = Property
    auth = ()

    def get(self) -> dict:
        properties = (
            Property.objects.filter(status=PropertyStatus.VACANT)
            .prefetch_related("photos")
            .exclude(models.Q(map_lat__isnull=True) | models.Q(map_lon__isnull=True))
        )
        features = []
        for prop in properties:
            photos = _ordered_photos(prop)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(prop.map_lon), float(prop.map_lat)],
                    },
                    "properties": {
                        "id": prop.id,
                        "name": prop.name,
                        "address": prop.address,
                        "rooms": prop.rooms,
                        "area_sqm": prop.area_sqm,
                        "floor": prop.floor,
                        "price": str(prop.ask_price),
                        "currency": prop.ask_currency,
                        "is_verified": prop.is_verified,
                        "image_url": _photo_url(photos[0], self.request) if photos else None,
                    },
                }
            )
        return self.ok({"type": "FeatureCollection", "features": features})


class DistrictListView(ListAPIView):
    model = District
    auth = ()

    def get_queryset(self):
        return District.objects.order_by("name")

    def get(self, parsed_query: Query[ListingFilterQuery]) -> dict:
        items = [{"id": d.id, "name": d.name, "city": d.city} for d in self.get_queryset()]
        return self.ok(items)


class AmenityListView(GenericController):
    model = Property
    auth = ()

    def get(self) -> dict:
        from property.models import Amenity

        items = [
            {"id": a.id, "slug": a.slug, "name": a.name, "icon": a.icon, "sort_order": a.sort_order}
            for a in Amenity.objects.filter(is_active=True).order_by("sort_order", "name")
        ]
        return self.ok(items)


class FaqListView(GenericController):
    model = FaqItem
    auth = ()

    def get(self) -> dict:
        items = [
            {"id": f.id, "question": f.question, "answer": f.answer, "sort_order": f.sort_order}
            for f in FaqItem.objects.filter(is_active=True).order_by("sort_order", "id")
        ]
        return self.ok(items)


class BookViewingView(GenericController):
    model = Listing
    auth = ()

    def get_queryset(self):
        return Listing.objects.filter(is_active=True).all()

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[ViewingRequestCreateInput]) -> dict:
        listing = self.get_object(pk=parsed_path.pk)
        vr = ViewingRequest.objects.create(listing=listing, **parsed_body.model_dump())
        return self.ok(
            {
                "id": vr.id,
                "listing_id": vr.listing_id,
                "full_name": vr.full_name,
                "phone": vr.phone,
                "email": vr.email,
                "preferred_date": vr.preferred_date.isoformat(),
                "preferred_time": vr.preferred_time,
                "message": vr.message,
                "status": vr.status,
                "created_at": vr.created_at.isoformat(),
                "updated_at": vr.updated_at.isoformat(),
            }
        )


class ContactInquiryView(BaseController):
    auth = ()

    def post(self, parsed_body: Body[ContactInquiryCreateInput]) -> dict:
        from account.models import User
        from notification.services import notify

        from core.constants import NotificationType, UserRole

        data = parsed_body.model_dump()
        listing_id = data.pop("listing_id", None)
        if listing_id is not None and not Listing.objects.filter(pk=listing_id).exists():
            listing_id = None
        inquiry = ContactInquiry.objects.create(listing_id=listing_id, **data)
        # Make the lead actionable: notify management so it surfaces in the app,
        # not only in the Django admin.
        for manager in User.objects.filter(role=UserRole.MANAGEMENT, is_active=True):
            notify(
                recipient=manager,
                type=NotificationType.GENERAL,
                title=str(_("New contact inquiry")),
                body=str(_("%(name)s sent a message via the marketplace.")) % {"name": inquiry.full_name},
                related_object_type="contact_inquiry",
                related_object_id=inquiry.id,
            )
        return self.ok(
            {
                "id": inquiry.id,
                "listing_id": inquiry.listing_id,
                "full_name": inquiry.full_name,
                "phone": inquiry.phone,
                "email": inquiry.email,
                "message": inquiry.message,
                "status": inquiry.status,
                "created_at": inquiry.created_at.isoformat(),
                "updated_at": inquiry.updated_at.isoformat(),
            }
        )
