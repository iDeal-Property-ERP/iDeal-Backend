import json
from decimal import Decimal
from http import HTTPStatus
from io import BytesIO

import pydantic
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from property.services.submission import PropertySubmissionError, PropertySubmissionService

from api.v1.owner.schemas import (
    OwnerListingResubmitPayload,
    OwnerListingSubmitPayload,
    OwnerOnboardingCreateInput,
    OwnerOnboardingOutput,
    OwnerPropertyOutput,
    OwnerSettlementOutput,
    PublicOfferOutput,
)
from core.api.permissions import RoleAuth
from core.api.views import BaseController, GenericController, ListAPIView, ListQuery
from core.constants import ListingStatus, PayoutStatus, PropertyStatus, UserRole

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
        from finance.models import OwnerSettlement, PayoutSchedule

        settlements = OwnerSettlement.objects.filter(owner=user)
        payouts = PayoutSchedule.objects.filter(owner=user)
        total_guaranteed = settlements.aggregate(total=Sum("owner_payout_amount"))["total"] or Decimal("0.00")
        total_paid = payouts.filter(status=PayoutStatus.PAID).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        total_pending = payouts.filter(status=PayoutStatus.SCHEDULED).aggregate(total=Sum("amount"))[
            "total"
        ] or Decimal("0.00")
        above = settlements.aggregate(total=Sum("owner_payout_amount") - Sum("gross_floor_amount"))["total"] or Decimal(
            "0.00"
        )
        next_payout = payouts.filter(status=PayoutStatus.SCHEDULED).order_by("scheduled_date").first()
        return self.ok(
            {
                "total_guaranteed": str(total_guaranteed),
                "total_paid": str(total_paid),
                "total_pending": str(total_pending),
                "total_above_guarantee": str(max(above, Decimal("0.00"))),
                "next_payout_amount": str(next_payout.amount if next_payout else Decimal("0.00")),
                "currency": "USD",
            }
        )


class OwnerWhyView(BaseController):
    auth = (RoleAuth(UserRole.OWNER),)

    def get(self) -> dict:
        return self.ok(
            {
                "title": str(_("Transparent guaranteed rental income")),
                "description": str(
                    _(
                        "Your agreement states a gross monthly floor and commission rate. "
                        "We pay the floor after commission even when rent is not collected; "
                        "when collected rent is higher, you receive percentage-based upside."
                    )
                ),
                "benefits": [
                    str(_("Statements show rent received, floor, commission and payout")),
                    str(_("No vacancy risk for your agreed net payout")),
                    str(_("Professional tenant screening and management")),
                    str(_("24/7 maintenance support")),
                    str(_("Regular property inspections and reports")),
                ],
            }
        )


class OwnerSettlementListView(ListAPIView):
    auth = (RoleAuth(UserRole.OWNER),)
    output_schema = OwnerSettlementOutput

    def get_queryset(self):
        from finance.models import OwnerSettlement

        return (
            OwnerSettlement.objects.filter(owner=self.request.user)
            .select_related("owner_agreement__property")
            .prefetch_related("payouts")
        )

    def to_output(self, settlement):
        payout = settlement.payouts.order_by("-created_at").first()
        return {
            "id": settlement.id,
            "property_name": settlement.owner_agreement.property.name,
            "period_start": settlement.period_start,
            "period_end": settlement.period_end,
            "gross_floor_amount": settlement.gross_floor_amount,
            "commission_rate": settlement.commission_rate,
            "currency": settlement.currency,
            "rent_received_amount": settlement.rent_received_amount,
            "settlement_base_amount": settlement.settlement_base_amount,
            "commission_amount": settlement.commission_amount,
            "owner_payout_amount": settlement.owner_payout_amount,
            "ideal_cash_exposure": settlement.ideal_cash_exposure,
            "payout_status": payout.status if payout else None,
            "payout_amount": payout.amount if payout else None,
            "payout_kind": payout.kind if payout else None,
        }

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


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
        if listing.status != ListingStatus.REJECTED:
            return self.fail(
                error=str(_("Only rejected listings can be edited/resubmitted")),
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


class OwnerListingListView(OwnerListingBaseView):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
        listings = self._owner_listings().order_by("-created_at")
        items = [self._build_output(listing) for listing in listings]
        if parsed_query.page is not None:
            from core.utils.pagination import build_paginated_response

            return self.ok(build_paginated_response(items, parsed_query.page, parsed_query.per_page))
        return self.ok(items)


class OwnerListingSubmitView(OwnerListingBaseView):
    def post(self) -> dict:
        payload_raw = self.request.POST.get("payload")
        if not payload_raw:
            return self.fail(error=str(_("Missing payload data")))

        payload_str = str(payload_raw) if not isinstance(payload_raw, str) else payload_raw

        try:
            data = json.loads(payload_str)
            validated = OwnerListingSubmitPayload.model_validate(data)
        except (json.JSONDecodeError, pydantic.ValidationError) as err:
            return self.fail(error=str(err), message=str(_("Invalid payload")))

        raw_files = self.request.FILES.getlist("images") if hasattr(self.request, "FILES") else []
        files = list(raw_files) if isinstance(raw_files, (list, tuple)) else []

        try:
            listing = PropertySubmissionService.submit_owner_listing(
                user=self.request.user,
                data=validated.model_dump(mode="json"),
                files=files,
            )
        except PropertySubmissionError as err:
            return self.fail(error=str(err), status_code=HTTPStatus.UNPROCESSABLE_ENTITY)
        except Exception as err:
            return self.fail(error=str(err), message=str(_("Failed to submit listing")))

        return self.ok(self._build_output(listing), status_code=HTTPStatus.CREATED)


class OwnerListingDetailView(OwnerListingBaseView):
    def get(self, parsed_path: Path[OwnerListingPath]) -> dict:
        listing = self._get_owned_listing(parsed_path.pk)
        return self.ok(self._build_output(listing))


class OwnerListingResubmitView(OwnerListingBaseView):
    def put(self, parsed_path: Path[OwnerListingPath]) -> dict:
        listing = self._get_owned_listing(parsed_path.pk)
        if listing.status != ListingStatus.REJECTED:
            return self.fail(
                error=str(_("Only rejected listings can be resubmitted")),
                message=str(_("Invalid status")),
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )

        payload_raw = None
        raw_files = []
        ct = self.request.META.get("CONTENT_TYPE", "") or getattr(self.request, "content_type", "")
        if "multipart" in ct.lower():
            try:
                from django.core.files.uploadhandler import MemoryFileUploadHandler
                from django.http.multipartparser import MultiPartParser

                meta = dict(self.request.META)
                body_bytes = self.request.body
                meta["CONTENT_LENGTH"] = str(len(body_bytes))
                handlers = [MemoryFileUploadHandler(self.request)]
                post, files_dict = MultiPartParser(meta, BytesIO(body_bytes), handlers).parse()
                payload_raw = post.get("payload")
                raw_files = files_dict.getlist("images")
                if not raw_files:
                    for k in files_dict:
                        raw_files.extend(files_dict.getlist(k))
            except Exception as parse_err:
                print("MULTIPART EXCEPTION:", repr(parse_err))
        elif hasattr(self.request, "data") and isinstance(self.request.data, dict):
            payload_raw = self.request.data.get("payload")
            raw_files = (
                self.request.data.getlist("images")
                if hasattr(self.request.data, "getlist")
                else self.request.data.get("images", [])
            )
        elif hasattr(self.request, "POST"):
            payload_raw = self.request.POST.get("payload")
            raw_files = self.request.FILES.getlist("images") if hasattr(self.request, "FILES") else []

        if not payload_raw:
            return self.fail(error=str(_("Missing payload data")))

        payload_str = str(payload_raw) if not isinstance(payload_raw, str) else payload_raw

        try:
            data = json.loads(payload_str)
            validated = OwnerListingResubmitPayload.model_validate(data)
        except (json.JSONDecodeError, pydantic.ValidationError) as err:
            return self.fail(error=str(err), message=str(_("Invalid payload")))

        files = list(raw_files) if isinstance(raw_files, (list, tuple)) else ([raw_files] if raw_files else [])

        try:
            listing = PropertySubmissionService.resubmit_rejected_listing(
                user=self.request.user,
                listing=listing,
                data=validated.model_dump(mode="json"),
                files=files,
            )
        except PropertySubmissionError as err:
            return self.fail(error=str(err), status_code=HTTPStatus.UNPROCESSABLE_ENTITY)
        except Exception as err:
            return self.fail(error=str(err), message=str(_("Failed to resubmit listing")))

        return self.ok(self._build_output(listing), status_code=HTTPStatus.OK)
