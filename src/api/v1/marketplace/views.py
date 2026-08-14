from __future__ import annotations

import pydantic
from django.db import models
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from marketplace.models import ContactInquiry, FaqItem, Listing, ViewingRequest
from marketplace.services.listings import (
    ListingFilters,
    apply_listing_filters,
    ordered_photos,
    photo_url,
    published_listings_queryset,
)
from property.models import District, Property

from api.v1.marketplace.schemas import (
    ContactInquiryCreateInput,
    ViewingRequestCreateInput,
)
from core.api.views import BaseController, DetailPath, GenericController, ListAPIView, RetrieveAPIView
from core.constants import ListingStatus, PropertyStatus
from core.utils.pagination import build_paginated_response
from core.utils.rate_limit import rate_limit

# Static verification checklist shown only on verified listing detail pages.
VERIFICATION_CHECKLIST = [
    {"key": "ownership", "label": _("Official ownership check")},
    {"key": "team", "label": _("Verified by iDeal team")},
    {"key": "contract", "label": _("In-app contract & payments")},
    {"key": "managed", "label": _("Managed end-to-end")},
]
RESPONSE_TIME = _("Usually responds within 1 hour")


def _amenities_brief(prop):
    return [{"slug": a.slug, "name": a.name, "icon": a.icon} for a in prop.amenities.all() if a.is_active]


def _verification_checklist(prop):
    if not prop.is_verified:
        return []
    return [{"key": item["key"], "label": str(item["label"])} for item in VERIFICATION_CHECKLIST]


def _build_property_brief(prop, request=None):
    photos = ordered_photos(prop)
    image_urls = [photo_url(p, request) for p in photos[:5]]
    return {
        "id": prop.id,
        "name": prop.name,
        "address": prop.address,
        "district_id": prop.district_id,
        "district_name": prop.district.name if prop.district else None,
        "property_type": prop.property_type,
        "engagement_type": prop.engagement_type,
        "rooms": prop.rooms,
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
    photos = ordered_photos(prop)
    monthly_price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
    deposit = listing.deposit_amount if listing.deposit_amount is not None else prop.deposit_amount
    output = _build_listing_output(listing, request)
    output.update(
        {
            "photos": [
                {
                    "id": p.id,
                    "image_url": photo_url(p, request),
                    "caption": p.caption or None,
                    "is_primary": p.is_primary,
                    "sort_order": p.sort_order,
                }
                for p in photos
            ],
            "specs": {
                "property_type": prop.property_type,
                "rooms": prop.rooms,
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
                "checklist": _verification_checklist(prop),
            },
        }
    )
    return output


ListingFilterQuery = ListingFilters


class ListingListView(ListAPIView):
    model = Listing
    auth = ()

    def get(self, parsed_query: Query[ListingFilterQuery]) -> dict:
        qs = apply_listing_filters(published_listings_queryset(), parsed_query)
        items = [_build_listing_output(obj, self.request) for obj in qs]
        paginated = build_paginated_response(items, parsed_query.page, parsed_query.per_page)
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
            photos = ordered_photos(prop)
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
                        "image_url": photo_url(photos[0], self.request) if photos else None,
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

    @rate_limit(requests=3, window_seconds=3600)
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
            }
        )

class PublicListingSubmitView(BaseController):
    auth = ()

    @rate_limit(requests=3, window_seconds=3600)
    def post(self) -> dict:
        import json
        import uuid

        from account.models import User
        from contract.models import OwnerOnboarding, PublicOffer
        from django.db import transaction
        from property.models import Amenity, PropertyPhoto

        from api.v1.marketplace.schemas import PublicListingSubmitInput
        from core.constants import UserRole
        from core.utils.uploads import UploadError, save_uploaded_images

        payload_str = self.request.POST.get("payload")
        if not payload_str:
            return self.fail(error=str(_("Missing payload data")))

        try:
            data = json.loads(payload_str)
            validated = PublicListingSubmitInput.model_validate(data)
        except (json.JSONDecodeError, pydantic.ValidationError) as e:
            return self.fail(error=str(e), message=str(_("Invalid payload")))

        files = self.request.FILES.getlist("images")
        if len(files) < 5:
            return self.fail(error=str(_("At least 5 photos are required")))

        contact = validated.contact

        try:
            with transaction.atomic():
                # Find or create user
                user = User.objects.filter(models.Q(email=contact.email) | models.Q(phone=contact.phone)).first()
                if not user:
                    user = User.objects.create(
                        username=str(uuid.uuid4())[:30],
                        email=contact.email,
                        phone=contact.phone,
                        first_name=contact.first_name,
                        last_name=contact.last_name,
                        role=UserRole.OWNER,
                        is_active=False,
                    )
                    user.set_unusable_password()
                    user.save(update_fields=["password"])

                # Create Property
                prop = Property.objects.create(
                    name=validated.name,
                    address=validated.name,  # Fallback to name if not provided
                    district_id=validated.district_id,
                    property_type=validated.property_type,
                    rooms=validated.rooms,
                    area_sqm=validated.area_sqm,
                    floor=validated.floor,
                    total_floors=validated.total_floors,
                    furnishing=validated.furnishing,
                    owner=user,
                    status=PropertyStatus.PENDING_REVIEW,
                    description=validated.description,
                    ask_price=validated.monthly_price,
                    ask_currency=validated.currency,
                    owner_guaranteed_price=validated.monthly_price,
                    owner_guaranteed_currency=validated.currency,
                    tenant_charge_price=validated.monthly_price,
                    tenant_charge_currency=validated.currency,
                )

                if validated.amenities:
                    prop.amenities.set(Amenity.objects.filter(slug__in=validated.amenities, is_active=True))

                # Create Listing
                listing = Listing.objects.create(
                    property=prop,
                    status=ListingStatus.PENDING_REVIEW,
                    is_active=False,
                    description=validated.description,
                    monthly_price=validated.monthly_price,
                    listed_price=validated.monthly_price,
                    deposit_amount=validated.deposit_amount,
                    currency=validated.currency,
                    minimum_stay=validated.minimum_stay,
                    price_includes=validated.price_includes,
                )

                # Accept Offer
                onboarding = OwnerOnboarding.objects.filter(property=prop).first()
                if not onboarding:
                    onboarding = OwnerOnboarding(owner=user, property=prop)
                    onboarding.accept_offer(PublicOffer.get_active())
                    onboarding.save()

                # Upload Photos
                try:
                    created_photos = save_uploaded_images(PropertyPhoto, "property", prop, files)
                    for idx, photo in enumerate(created_photos):
                        photo.sort_order = idx
                        photo.is_primary = (idx == 0)
                        photo.save(update_fields=["sort_order", "is_primary", "updated_at"])
                except UploadError as err:
                    raise ValueError(str(err)) from err

        except Exception as err:
            return self.fail(error=str(err), message=str(_("Failed to process listing submission")))

        return self.ok({"id": listing.id, "status": listing.status})
