from decimal import Decimal
from http import HTTPStatus

import pydantic
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query

from api.v1.owner.schemas import (
    OwnerListingCreateInput,
    OwnerListingPhotoReorderInput,
    OwnerListingSubmitInput,
    OwnerListingUpdateInput,
    OwnerOnboardingCreateInput,
    OwnerOnboardingOutput,
    OwnerPropertyOutput,
    PublicOfferOutput,
)
from core.api.permissions import RoleAuth
from core.api.views import BaseController, GenericController, ListAPIView, ListQuery
from core.constants import ListingStatus, PayoutStatus, PriceIncluded, PropertyStatus, UserRole

MIN_PHOTOS = 5


class OwnerPropertyListView(ListAPIView):
    auth = (RoleAuth(UserRole.OWNER),)
    output_schema = OwnerPropertyOutput

    def get_queryset(self):
        from property.models import Property

        user = self.request.user
        return Property.objects.filter(owner=user).select_related("district").order_by("-created_at")

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class OwnerEarningsView(BaseController):
    auth = (RoleAuth(UserRole.OWNER),)

    def get(self) -> dict:
        user = self.request.user
        from finance.models import PayoutSchedule
        from property.models import Property

        from core.constants import PropertyStatus

        by_property = PayoutSchedule.objects.filter(owner=user)
        # Only properties under an active guarantee count toward the guaranteed
        # figure — drafts and pending-review submissions are not yet guaranteed
        # and would otherwise overstate the owner's contractual minimum.
        managed_statuses = (PropertyStatus.RENTED, PropertyStatus.VACANT, PropertyStatus.MAINTENANCE)
        total_guaranteed = Property.objects.filter(owner=user, status__in=managed_statuses).aggregate(
            total=Sum("owner_guaranteed_price")
        )["total"] or Decimal("0.00")
        total_paid = by_property.filter(status=PayoutStatus.PAID).aggregate(total=Sum("amount"))["total"] or Decimal(
            "0.00"
        )
        total_pending = by_property.filter(status=PayoutStatus.SCHEDULED).aggregate(total=Sum("amount"))[
            "total"
        ] or Decimal("0.00")
        return self.ok(
            {
                "total_guaranteed": str(total_guaranteed),
                "total_paid": str(total_paid),
                "total_pending": str(total_pending),
                "currency": "USD",
            }
        )


class OwnerWhyView(BaseController):
    auth = (RoleAuth(UserRole.OWNER),)

    def get(self) -> dict:
        return self.ok(
            {
                "title": str(_("Guaranteed Rental Income")),
                "description": str(
                    _(
                        "With iDeal, you receive your rental income every month, "
                        "on time, regardless of whether the property is occupied. "
                        "We handle tenant management, maintenance, and legal compliance."
                    )
                ),
                "benefits": [
                    str(_("Monthly payouts on the 25th of every month")),
                    str(_("No vacancy risk — we guarantee your income")),
                    str(_("Professional tenant screening and management")),
                    str(_("24/7 maintenance support")),
                    str(_("Regular property inspections and reports")),
                ],
            }
        )


class OwnerPublicOfferView(BaseController):
    auth = (RoleAuth(UserRole.OWNER),)

    def get(self) -> dict:
        from contract.models import PublicOffer

        offer = PublicOffer.get_active()
        if offer is None:
            return self.ok({"id": None, "version": None, "body": None})
        return self.ok(PublicOfferOutput.model_validate(offer).model_dump(mode="json"))


class OwnerOnboardingView(GenericController):
    auth = (RoleAuth(UserRole.OWNER),)
    output_schema = OwnerOnboardingOutput

    def get_queryset(self):
        from contract.models import OwnerOnboarding

        return (
            OwnerOnboarding.objects.filter(owner=self.request.user).select_related("property").order_by("-created_at")
        )

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return self.list_response(self.get_queryset(), parsed_query)

    def post(self, parsed_body: Body[OwnerOnboardingCreateInput]) -> dict:
        user = self.request.user
        if not parsed_body.accept_offer:
            return self.fail(
                error=str(_("You must accept the public offer to submit a property")),
                status_code=400,
            )

        from contract.models import OwnerOnboarding, PublicOffer
        from property.models import Property

        prop = Property.objects.create(
            name=parsed_body.name,
            address=parsed_body.address,
            district_id=parsed_body.district_id,
            rooms=parsed_body.rooms,
            area_sqm=parsed_body.area_sqm,
            floor=parsed_body.floor,
            total_floors=parsed_body.total_floors,
            owner=user,
            status=PropertyStatus.PENDING_REVIEW,
            description=parsed_body.description,
            ask_price=parsed_body.ask_price,
            ask_currency=parsed_body.ask_currency,
            # Placeholder pricing — management finalizes these at approval.
            owner_guaranteed_price=parsed_body.ask_price,
            owner_guaranteed_currency=parsed_body.ask_currency,
            tenant_charge_price=parsed_body.ask_price,
            tenant_charge_currency=parsed_body.ask_currency,
        )

        onboarding = OwnerOnboarding(owner=user, property=prop)
        onboarding.accept_offer(PublicOffer.get_active())
        onboarding.save()
        return self.ok(self.to_output(onboarding))


# --- List-Your-Property wizard ------------------------------------------------


def _ordered_photos(prop):
    return sorted(prop.photos.all(), key=lambda p: (not p.is_primary, p.sort_order))


def _photo_url(photo, request):
    url = photo.image.url
    return request.build_absolute_uri(url) if request is not None else url


class OwnerListingPath(pydantic.BaseModel):
    pk: int


class OwnerListingPhotoPath(pydantic.BaseModel):
    pk: int
    photo_id: int


class OwnerListingBaseView(GenericController):
    """Shared owner-scoping + output building for wizard endpoints."""

    auth = (RoleAuth(UserRole.OWNER),)

    def _owner_listings(self):
        from marketplace.models import Listing

        return (
            Listing.objects.select_related("property__district")
            .prefetch_related("property__photos", "property__amenities")
            .filter(property__owner=self.request.user)
        )

    def _get_owned_listing(self, pk):
        listing = self._owner_listings().filter(pk=pk).first()
        if listing is None:
            return self.fail(error=str(_("Listing not found")), status_code=HTTPStatus.NOT_FOUND)
        return listing

    def _require_editable(self, listing):
        if listing.status not in (ListingStatus.DRAFT, ListingStatus.REJECTED):
            return self.fail(
                error=str(_("Only draft or rejected listings can be edited")),
                message=str(_("Listing is not editable")),
            )

    def _build_output(self, listing):
        from contract.models import OwnerOnboarding

        prop = listing.property
        photos = _ordered_photos(prop)
        photo_count = len(photos)
        monthly_price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
        return {
            "id": listing.id,
            "status": listing.status,
            "property_id": prop.id,
            "property_type": prop.property_type,
            "name": prop.name,
            "address": prop.address,
            "district_id": prop.district_id,
            "district_name": prop.district.name if prop.district else None,
            "rooms": prop.rooms,
            "bathrooms": prop.bathrooms,
            "area_sqm": prop.area_sqm,
            "floor": prop.floor,
            "total_floors": prop.total_floors,
            "furnishing": prop.furnishing,
            "tariff": prop.tariff,
            "description": prop.description,
            "amenities": [{"slug": a.slug, "name": a.name, "icon": a.icon} for a in prop.amenities.all()],
            "monthly_price": str(monthly_price) if monthly_price is not None else None,
            "deposit_amount": str(listing.deposit_amount) if listing.deposit_amount is not None else None,
            "currency": listing.currency,
            "minimum_stay": listing.minimum_stay,
            "price_includes": listing.price_includes or [],
            "photos": [
                {
                    "id": p.id,
                    "image_url": _photo_url(p, self.request),
                    "caption": p.caption or None,
                    "is_primary": p.is_primary,
                    "sort_order": p.sort_order,
                }
                for p in photos
            ],
            "completeness": {
                "has_5_photos": photo_count >= MIN_PHOTOS,
                "has_price": monthly_price is not None and listing.deposit_amount is not None,
                "has_ownership": OwnerOnboarding.objects.filter(property=prop).exists(),
            },
            "rejection_reason": listing.rejection_reason,
            "created_at": listing.created_at.isoformat(),
            "updated_at": listing.updated_at.isoformat(),
        }

    def _set_amenities(self, prop, slugs):
        from property.models import Amenity

        prop.amenities.set(Amenity.objects.filter(slug__in=slugs, is_active=True))


class OwnerListingListCreateView(OwnerListingBaseView):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
        listings = self._owner_listings().order_by("-created_at")
        items = [self._build_output(listing) for listing in listings]
        if parsed_query.page is not None:
            from core.utils.pagination import build_paginated_response

            return self.ok(build_paginated_response(items, parsed_query.page, parsed_query.per_page))
        return self.ok(items)

    def post(self, parsed_body: Body[dict]) -> dict:
        from marketplace.models import Listing
        from property.models import District, Property

        data = self._validate_body(OwnerListingCreateInput, parsed_body)
        amenities = data.pop("amenities", [])
        district = District.objects.filter(pk=data["district_id"]).first()
        if district is None:
            return self.fail(error=str(_("District not found")), status_code=HTTPStatus.NOT_FOUND)

        prop = Property.objects.create(
            name=data["name"],
            address=data.get("address") or district.name,
            district_id=data["district_id"],
            property_type=data["property_type"],
            rooms=data["rooms"],
            bathrooms=data["bathrooms"],
            area_sqm=data["area_sqm"],
            floor=data["floor"],
            total_floors=data.get("total_floors"),
            furnishing=data["furnishing"],
            owner=self.request.user,
            status=PropertyStatus.PENDING_REVIEW,
            description=data.get("description"),
            # Placeholder pricing — set at the Pricing step and finalized by management.
            ask_price=Decimal("0"),
            owner_guaranteed_price=Decimal("0"),
            tenant_charge_price=Decimal("0"),
        )
        if amenities:
            self._set_amenities(prop, amenities)
        # Property is PENDING_REVIEW so the auto-listing signal does not fire — create the draft.
        listing = Listing.objects.create(
            property=prop,
            status=ListingStatus.DRAFT,
            is_active=False,
            description=data.get("description"),
        )
        return self.ok(self._build_output(listing), status_code=HTTPStatus.CREATED)


class OwnerListingDetailView(OwnerListingBaseView):
    def get(self, parsed_path: Path[OwnerListingPath]) -> dict:
        listing = self._get_owned_listing(parsed_path.pk)
        return self.ok(self._build_output(listing))

    def patch(self, parsed_path: Path[OwnerListingPath], parsed_body: Body[dict]) -> dict:
        listing = self._get_owned_listing(parsed_path.pk)
        self._require_editable(listing)
        data = self._validate_body(OwnerListingUpdateInput, parsed_body, exclude_unset=True)
        prop = listing.property

        property_fields = {
            "property_type": "property_type",
            "name": "name",
            "address": "address",
            "district_id": "district_id",
            "rooms": "rooms",
            "bathrooms": "bathrooms",
            "area_sqm": "area_sqm",
            "floor": "floor",
            "total_floors": "total_floors",
            "furnishing": "furnishing",
            "tariff": "tariff",
            "description": "description",
        }
        for key, attr in property_fields.items():
            if key in data:
                setattr(prop, attr, data[key])

        # Pricing (step 3) mirrors onto the property's pricing columns.
        if "monthly_price" in data and data["monthly_price"] is not None:
            price = data["monthly_price"]
            listing.monthly_price = price
            listing.listed_price = price
            prop.ask_price = price
            prop.tenant_charge_price = price
            prop.owner_guaranteed_price = price
        if "deposit_amount" in data:
            listing.deposit_amount = data["deposit_amount"]
            prop.deposit_amount = data["deposit_amount"]
        if "currency" in data and data["currency"]:
            listing.currency = data["currency"]
            prop.ask_currency = data["currency"]
        if "minimum_stay" in data:
            listing.minimum_stay = data["minimum_stay"]
        if "price_includes" in data and data["price_includes"] is not None:
            valid = set(PriceIncluded.values())
            listing.price_includes = [slug for slug in data["price_includes"] if slug in valid]

        prop.save()
        if "amenities" in data and data["amenities"] is not None:
            self._set_amenities(prop, data["amenities"])
        listing.save()
        return self.ok(self._build_output(listing))


class OwnerListingPhotosView(OwnerListingBaseView):
    def post(self, parsed_path: Path[OwnerListingPath]) -> dict:
        from property.models import PropertyPhoto

        from core.utils.uploads import UploadError, save_uploaded_images

        listing = self._get_owned_listing(parsed_path.pk)
        self._require_editable(listing)
        files = self.request.FILES.getlist("images")
        if not files:
            return self.fail(error=str(_("No images provided")))

        prop = listing.property
        existing = prop.photos.count()
        try:
            created = save_uploaded_images(PropertyPhoto, "property", prop, files)
        except UploadError as err:
            return self.fail(error=str(err))

        # Ensure exactly one primary + stable ordering.
        for idx, photo in enumerate(created):
            photo.sort_order = existing + idx
            photo.is_primary = existing == 0 and idx == 0
            photo.save(update_fields=["sort_order", "is_primary", "updated_at"])

        data = [
            {
                "id": p.id,
                "image_url": _photo_url(p, self.request),
                "caption": p.caption or None,
                "is_primary": p.is_primary,
                "sort_order": p.sort_order,
            }
            for p in created
        ]
        return self.ok(data, status_code=HTTPStatus.CREATED)


class OwnerListingPhotoReorderView(OwnerListingBaseView):
    def patch(self, parsed_path: Path[OwnerListingPath], parsed_body: Body[OwnerListingPhotoReorderInput]) -> dict:
        listing = self._get_owned_listing(parsed_path.pk)
        self._require_editable(listing)
        prop = listing.property
        photo_map = {p.id: p for p in prop.photos.all()}
        for item in parsed_body.items:
            photo = photo_map.get(item.id)
            if photo is None:
                continue
            photo.sort_order = item.sort_order
            photo.is_primary = item.is_primary
            fields = ["sort_order", "is_primary", "updated_at"]
            if item.caption is not None:
                photo.caption = item.caption
                fields.append("caption")
            photo.save(update_fields=fields)
        listing.refresh_from_db()
        return self.ok(self._build_output(listing))


class OwnerListingPhotoDeleteView(OwnerListingBaseView):
    def delete(self, parsed_path: Path[OwnerListingPhotoPath]) -> dict:
        listing = self._get_owned_listing(parsed_path.pk)
        self._require_editable(listing)
        photo = listing.property.photos.filter(pk=parsed_path.photo_id).first()
        if photo is None:
            return self.fail(error=str(_("Photo not found")), status_code=HTTPStatus.NOT_FOUND)
        was_primary = photo.is_primary
        photo.delete()
        # If the cover photo was removed, promote the next remaining photo so the
        # listing never ends up with no primary image.
        if was_primary:
            successor = listing.property.photos.order_by("sort_order", "id").first()
            if successor is not None and not successor.is_primary:
                successor.is_primary = True
                successor.save(update_fields=["is_primary"])
        return self.ok({"deleted": True})


class OwnerListingSubmitView(OwnerListingBaseView):
    def post(self, parsed_path: Path[OwnerListingPath], parsed_body: Body[OwnerListingSubmitInput]) -> dict:
        from contract.models import OwnerOnboarding, PublicOffer

        listing = self._get_owned_listing(parsed_path.pk)
        self._require_editable(listing)

        if not parsed_body.accept_offer:
            return self.fail(error=str(_("You must accept the public offer to publish")))

        prop = listing.property
        errors = []
        if prop.photos.count() < MIN_PHOTOS:
            errors.append(str(_("At least 5 photos are required")))
        if listing.monthly_price is None:
            errors.append(str(_("A monthly price is required")))
        if listing.deposit_amount is None:
            errors.append(str(_("A deposit amount is required")))
        if errors:
            return self.fail(error=errors, message=str(_("Listing is incomplete")))

        # Reuse the onboarding flow (public-offer acceptance) if not already onboarded.
        if not OwnerOnboarding.objects.filter(property=prop).exists():
            onboarding = OwnerOnboarding(owner=self.request.user, property=prop)
            onboarding.accept_offer(PublicOffer.get_active())
            onboarding.save()

        listing.status = ListingStatus.PENDING_REVIEW
        listing.submitted_at = timezone.now()
        listing.save(update_fields=["status", "submitted_at", "updated_at"])
        return self.ok(self._build_output(listing))
