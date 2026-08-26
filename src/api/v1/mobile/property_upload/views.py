from __future__ import annotations

import json
from http import HTTPStatus
from typing import cast

import pydantic
from account.models import User
from contract.models import PublicOffer
from django.utils.translation import gettext_lazy as _
from property.models import Amenity, District
from property.services.submission import PropertySubmissionError, PropertySubmissionService

from api.v1.mobile.home.views import get_optional_authenticated_user
from api.v1.mobile.property_upload.schemas import (
    AmenityItem,
    ChoiceItem,
    DistrictItem,
    MobilePropertyUploadConfigOutput,
    MobilePropertyUploadInput,
    MobilePropertyUploadOutput,
    PublicOfferItem,
    UserProfileItem,
)
from core.api.permissions import BlacklistAwareJWTSyncAuth
from core.api.views import BaseController
from core.constants import (
    Currency,
    FurnishingType,
    MinimumStay,
    PriceIncluded,
    PropertyType,
)

MIN_PHOTOS = 5


class MobilePropertyUploadConfigView(BaseController):
    auth = ()

    def get(self) -> dict:
        districts = [
            DistrictItem(id=d.id, name=str(d.name), city=str(d.city))
            for d in District.objects.filter(deleted_at__isnull=True).order_by("name")
        ]
        amenities = [
            AmenityItem(slug=str(a.slug), name=str(a.name), icon=str(a.icon))
            for a in Amenity.objects.filter(is_active=True).order_by("sort_order", "name")
        ]
        property_types = [ChoiceItem(value=val, label=str(_(lbl))) for val, lbl in PropertyType.CHOICES]
        furnishings = [ChoiceItem(value=val, label=str(_(lbl))) for val, lbl in FurnishingType.CHOICES]
        minimum_stays = [val for val, _ in MinimumStay.CHOICES]
        price_includes = [ChoiceItem(value=val, label=str(_(lbl))) for val, lbl in PriceIncluded.CHOICES]
        currencies = Currency.values()

        active_offer = PublicOffer.get_active()
        public_offer = (
            PublicOfferItem(
                id=active_offer.id,
                version=str(active_offer.version) if active_offer.version else None,
                body=str(active_offer.body) if active_offer.body else None,
            )
            if active_offer
            else PublicOfferItem()
        )

        user_raw = get_optional_authenticated_user(self.request)
        user = cast(User, user_raw) if user_raw else None
        user_profile = (
            UserProfileItem(
                first_name=str(user.first_name) if getattr(user, "first_name", None) else None,
                last_name=str(user.last_name) if getattr(user, "last_name", None) else None,
                email=str(user.email) if getattr(user, "email", None) else None,
                phone=str(user.phone) if getattr(user, "phone", None) else None,
            )
            if user
            else None
        )

        output = MobilePropertyUploadConfigOutput(
            property_types=property_types,
            districts=districts,
            furnishings=furnishings,
            amenities=amenities,
            minimum_stays=minimum_stays,
            price_includes=price_includes,
            currencies=currencies,
            public_offer=public_offer,
            user_profile=user_profile,
        )
        return self.ok(output.model_dump(mode="json"))


class MobilePropertyUploadSubmitView(BaseController):
    auth = (BlacklistAwareJWTSyncAuth(),)

    def post(self) -> dict:
        payload_raw = self.request.POST.get("payload")
        if not payload_raw:
            return self.fail(error=str(_("Missing payload data")))

        payload_str = str(payload_raw) if not isinstance(payload_raw, str) else payload_raw

        try:
            data = json.loads(payload_str)
            validated = MobilePropertyUploadInput.model_validate(data)
        except (json.JSONDecodeError, pydantic.ValidationError) as err:
            return self.fail(error=str(err), message=str(_("Invalid payload")))

        raw_files = self.request.FILES.getlist("images") if hasattr(self.request, "FILES") else []
        files = list(raw_files) if isinstance(raw_files, (list, tuple)) else []
        if len(files) < MIN_PHOTOS:
            return self.fail(error=str(_("At least 5 photos are required")))

        if not validated.accept_offer:
            return self.fail(error=str(_("You must accept the public offer to submit a property")))

        district = District.objects.filter(pk=validated.district_id, deleted_at__isnull=True).first()
        if district is None:
            return self.fail(error=str(_("District not found")), status_code=HTTPStatus.NOT_FOUND)

        user = cast(User, self.request.user)  # type: ignore[attr-defined]

        try:
            listing = PropertySubmissionService.submit_owner_listing(
                user=user,
                data=validated.model_dump(mode="json"),
                files=files,
            )
        except PropertySubmissionError as err:
            return self.fail(error=str(err), status_code=HTTPStatus.UNPROCESSABLE_ENTITY)
        except Exception as err:
            return self.fail(error=str(err), message=str(_("Failed to process property upload")))

        return self.ok(
            MobilePropertyUploadOutput(
                id=listing.id,
                property_id=listing.property_id,
                status=listing.status,
                message=str(_("Listing submitted for review")),
            ).model_dump(mode="json"),
            status_code=HTTPStatus.CREATED,
        )
