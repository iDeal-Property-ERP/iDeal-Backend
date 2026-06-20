from __future__ import annotations

import pydantic
from django.db import models
from dmr import Body, Path, Query
from marketplace.models import Listing, ViewingRequest
from property.models import Property

from api.v1.marketplace.schemas import (
    ViewingRequestCreateInput,
)
from core.api.views import DetailPath, GenericController, ListAPIView, RetrieveAPIView
from core.constants import PropertyStatus
from core.utils.pagination import build_paginated_response


def _photo_url(photo, request):
    """Build an absolute URL for a property photo, falling back to the relative media URL."""
    url = photo.image.url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


def _ordered_photos(prop):
    """Photos ordered primary-first, then by sort_order (uses prefetched cache when available)."""
    return sorted(prop.photos.all(), key=lambda p: (not p.is_primary, p.sort_order))


def _build_property_brief(prop, request=None):
    photos = _ordered_photos(prop)
    image_urls = [_photo_url(p, request) for p in photos[:5]]
    return {
        "id": prop.id,
        "name": prop.name,
        "address": prop.address,
        "district_id": prop.district_id,
        "district_name": prop.district.name if prop.district else None,
        "rooms": prop.rooms,
        "area_sqm": prop.area_sqm,
        "floor": prop.floor,
        "total_floors": prop.total_floors,
        "status": prop.status,
        "map_lat": str(prop.map_lat) if prop.map_lat is not None else None,
        "map_lon": str(prop.map_lon) if prop.map_lon is not None else None,
        "tariff": prop.tariff,
        "ask_price": str(prop.ask_price),
        "ask_currency": prop.ask_currency,
        "image_url": image_urls[0] if image_urls else None,
        "image_urls": image_urls,
    }


def _build_listing_output(listing, request=None):
    return {
        "id": listing.id,
        "property": _build_property_brief(listing.property, request),
        "property_id": listing.property_id,
        "owner_agreement_id": listing.owner_agreement_id,
        "is_active": listing.is_active,
        "is_featured": listing.is_featured,
        "description": listing.description,
        "listed_price": str(listing.listed_price) if listing.listed_price is not None else None,
        "created_at": listing.created_at.isoformat(),
        "updated_at": listing.updated_at.isoformat(),
    }


class ListingFilterQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20
    district_id: int | None = None
    price_min: float | None = None
    price_max: float | None = None
    rooms: int | None = None
    area_min: int | None = None
    area_max: int | None = None


class ListingListView(ListAPIView):
    model = Listing
    auth = ()

    def get_queryset(self):
        return (
            Listing.objects.select_related("property__district")
            .prefetch_related("property__photos")
            .filter(is_active=True, property__status=PropertyStatus.VACANT)
            .order_by("-is_featured", "-created_at")
        )

    def get(self, parsed_query: Query[ListingFilterQuery]) -> dict:
        qs = self.get_queryset()
        if parsed_query.district_id is not None:
            qs = qs.filter(property__district_id=parsed_query.district_id)
        if parsed_query.price_min is not None:
            qs = qs.filter(listed_price__gte=parsed_query.price_min)
        if parsed_query.price_max is not None:
            qs = qs.filter(listed_price__lte=parsed_query.price_max)
        if parsed_query.rooms is not None:
            qs = qs.filter(property__rooms=parsed_query.rooms)
        if parsed_query.area_min is not None:
            qs = qs.filter(property__area_sqm__gte=parsed_query.area_min)
        if parsed_query.area_max is not None:
            qs = qs.filter(property__area_sqm__lte=parsed_query.area_max)
        items = [_build_listing_output(obj, self.request) for obj in qs]
        if parsed_query.page is not None:
            paginated = build_paginated_response(items, parsed_query.page, parsed_query.per_page)
            return self.ok(paginated)
        return self.ok(items)


class ListingDetailView(RetrieveAPIView):
    model = Listing
    auth = ()

    def get_queryset(self):
        return Listing.objects.select_related("property__district").prefetch_related("property__photos").all()

    def get(self, parsed_path: Path[DetailPath]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        return self.ok(_build_listing_output(instance, self.request))


class ListingMapView(GenericController):
    model = Property
    auth = ()

    def get(self) -> dict:
        properties = Property.objects.filter(status=PropertyStatus.VACANT).prefetch_related("photos").exclude(
            models.Q(map_lat__isnull=True) | models.Q(map_lon__isnull=True)
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
                        "image_url": _photo_url(photos[0], self.request) if photos else None,
                    },
                }
            )
        return self.ok({"type": "FeatureCollection", "features": features})


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
                "message": vr.message,
                "status": vr.status,
                "created_at": vr.created_at.isoformat(),
                "updated_at": vr.updated_at.isoformat(),
            }
        )
