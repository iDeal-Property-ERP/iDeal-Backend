from __future__ import annotations

import logging
from decimal import Decimal
from io import BytesIO
from typing import Any

from account.models import User
from contract.models import OwnerOnboarding, PublicOffer
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone
from marketplace.models import Listing
from PIL import Image
from property.models import (
    Amenity,
    District,
    OneOffDeal,
    Property,
    PropertyPhoto,
    VerificationVisit,
)
from property.services.validation import validate_floor_bounds

from core.constants import (
    BrokerageCommissionType,
    Currency,
    FurnishingType,
    ListingStatus,
    OneOffChannel,
    OneOffDealStatus,
    PriceIncluded,
    PropertyEngagementType,
    PropertyStatus,
    PropertyType,
    TariffChoices,
    UserRole,
)

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_FORMAT_MAPPING = {
    "JPEG": ("image/jpeg", (".jpg", ".jpeg")),
    "PNG": ("image/png", (".png",)),
    "WEBP": ("image/webp", (".webp",)),
}


class PropertySubmissionError(ValueError):
    """Raised when submission input or files fail validation."""


def validate_image_file(file: UploadedFile) -> str:
    """Validate image size, decode via Pillow, and verify MIME/extension/format consistency."""
    if file.size > MAX_IMAGE_BYTES:
        raise PropertySubmissionError(f"Image '{file.name}' exceeds the 10 MB limit.")

    try:
        content = file.read()
        file.seek(0)
        img = Image.open(BytesIO(content))
        img.verify()
    except Exception as err:
        raise PropertySubmissionError(f"Image '{file.name}' is corrupt or cannot be decoded.") from err

    fmt = (img.format or "").upper()
    if fmt not in ALLOWED_FORMAT_MAPPING:
        raise PropertySubmissionError(f"Image '{file.name}' format '{fmt}' is not supported. Use JPEG, PNG, or WebP.")

    expected_mime, valid_exts = ALLOWED_FORMAT_MAPPING[fmt]
    content_type = getattr(file, "content_type", None)
    if content_type and content_type.lower() != expected_mime:
        raise PropertySubmissionError(
            f"Image '{file.name}' MIME type '{content_type}' does not match actual image format '{fmt}'."
        )

    file_name = file.name or ""
    ext = ("." + file_name.rsplit(".", 1)[-1].lower()) if "." in file_name else ""
    if ext not in valid_exts:
        raise PropertySubmissionError(
            f"Image '{file.name}' extension '{ext}' does not match actual image format '{fmt}'."
        )

    return fmt


def validate_images(files: list[UploadedFile], *, min_photos: int = 5, max_photos: int = 12) -> None:
    if len(files) < min_photos:
        raise PropertySubmissionError(f"At least {min_photos} photos are required (received {len(files)}).")
    if len(files) > max_photos:
        raise PropertySubmissionError(f"At most {max_photos} photos are allowed (received {len(files)}).")
    for f in files:
        validate_image_file(f)


class PropertySubmissionService:
    @staticmethod
    def submit_managed_by_management(
        *,
        user: User,
        data: dict[str, Any],
        files: list[UploadedFile],
        schedule_verification_at: str | None = None,
    ) -> Property:
        validate_images(files, min_photos=5, max_photos=12)

        district_id = data.get("district_id")
        district = District.objects.filter(pk=district_id, deleted_at__isnull=True).first()
        if not district:
            raise PropertySubmissionError("District not found.")

        owner_id = data.get("owner_id")
        owner = User.objects.filter(pk=owner_id).first() if owner_id else None

        floor = data.get("floor")
        total_floors = data.get("total_floors")
        validate_floor_bounds(floor, total_floors)

        ask_price = data.get("ask_price")
        if ask_price is None or Decimal(str(ask_price)) < 0:
            raise PropertySubmissionError("Ask price must be non-negative.")

        created_files_to_cleanup: list[PropertyPhoto] = []

        try:
            with transaction.atomic():
                prop_name = data.get("name") or f"{data.get('rooms')}-room property in {district.name}"
                prop_desc = data.get("description", "")
                content_locale = data.get("content_locale") or "en"
                prop = Property.objects.create(
                    name=prop_name,
                    name_en=prop_name,
                    name_uz=prop_name,
                    name_ru=prop_name,
                    address=data.get("address") or district.name,
                    district=district,
                    property_type=data.get("property_type", PropertyType.APARTMENT),
                    rooms=data.get("rooms"),
                    area_sqm=data.get("area_sqm"),
                    floor=floor,
                    total_floors=total_floors,
                    furnishing=data.get("furnishing", FurnishingType.UNFURNISHED),
                    owner=owner,
                    engagement_type=PropertyEngagementType.MANAGED,
                    status=PropertyStatus.VACANT,
                    description=prop_desc,
                    description_en=prop_desc,
                    description_uz=prop_desc,
                    description_ru=prop_desc,
                    tariff=data.get("tariff", TariffChoices.STANDARD),
                    map_lat=data.get("map_lat"),
                    map_lon=data.get("map_lon"),
                    ask_price=ask_price,
                    ask_currency=data.get("ask_currency", "USD"),
                    owner_guaranteed_price=data.get("owner_guaranteed_price", ask_price),
                    owner_guaranteed_currency=data.get("owner_guaranteed_currency", data.get("ask_currency", "USD")),
                    tenant_charge_price=data.get("tenant_charge_price", ask_price),
                    tenant_charge_currency=data.get("tenant_charge_currency", data.get("ask_currency", "USD")),
                    deposit_amount=data.get("deposit_amount", Decimal("0.00")),
                    deposit_currency=data.get("deposit_currency", "USD"),
                    vacant_since=timezone.now().date(),
                    vacant_days=0,
                )

                if "translations" in data and isinstance(data["translations"], dict):
                    from core.services.localization import LocalizedContentService

                    LocalizedContentService().apply_translations(prop, data["translations"], ["name", "description"])
                    prop.save()

                amenity_slugs = data.get("amenities") or []
                if amenity_slugs:
                    prop.amenities.set(Amenity.objects.filter(slug__in=amenity_slugs, is_active=True))

                # Listing for marketplace
                Listing.objects.update_or_create(
                    property=prop,
                    defaults={
                        "status": ListingStatus.PUBLISHED,
                        "is_active": True,
                        "description": prop.description,
                        "description_en": getattr(prop, "description_en", prop.description),
                        "description_uz": getattr(prop, "description_uz", prop.description),
                        "description_ru": getattr(prop, "description_ru", prop.description),
                        "monthly_price": prop.ask_price,
                        "listed_price": prop.ask_price,
                        "deposit_amount": prop.deposit_amount,
                        "currency": prop.ask_currency,
                        "minimum_stay": data.get("minimum_stay", 6),
                        "price_includes": data.get("price_includes", []),
                        "published_at": timezone.now(),
                    },
                )

                if owner:
                    onboarding = OwnerOnboarding(owner=owner, property=prop)
                    active_offer = PublicOffer.get_active()
                    if active_offer:
                        onboarding.accept_offer(active_offer, locale=content_locale)
                    onboarding.save()

                if schedule_verification_at:
                    VerificationVisit.objects.create(
                        property=prop,
                        scheduled_for=schedule_verification_at,
                        scheduled_by=user,
                    )

                # Save photos
                captions = data.get("captions") or []
                for idx, file_obj in enumerate(files):
                    photo = PropertyPhoto(
                        property=prop,
                        image=file_obj,
                        caption=captions[idx] if idx < len(captions) and captions[idx] else "",
                        is_primary=(idx == 0),
                        sort_order=idx,
                    )
                    photo.save()
                    created_files_to_cleanup.append(photo)

        except Exception as err:
            for photo in created_files_to_cleanup:
                try:
                    if photo.image:
                        photo.image.delete(save=False)
                    if photo.preview_image:
                        photo.preview_image.delete(save=False)
                    if photo.display_image:
                        photo.display_image.delete(save=False)
                except Exception:
                    pass
            raise err

        return prop

    @staticmethod
    def submit_one_off_by_management(
        *,
        user: User,
        data: dict[str, Any],
        brokerage: dict[str, Any],
        files: list[UploadedFile],
    ) -> Property:
        channel = brokerage.get("channel", OneOffChannel.MARKETPLACE)
        is_marketplace = channel == OneOffChannel.MARKETPLACE

        if is_marketplace:
            validate_images(files, min_photos=5, max_photos=12)
        elif files:
            validate_images(files, min_photos=0, max_photos=12)

        district_id = data.get("district_id")
        district = District.objects.filter(pk=district_id, deleted_at__isnull=True).first()
        if not district:
            raise PropertySubmissionError("District not found.")

        floor = data.get("floor")
        total_floors = data.get("total_floors")
        validate_floor_bounds(floor, total_floors)

        ask_price = data.get("ask_price")
        if ask_price is None or Decimal(str(ask_price)) < 0:
            raise PropertySubmissionError("Ask price must be non-negative.")

        # Commission validation
        comm_type = brokerage.get("commission_type", BrokerageCommissionType.NONE)
        fixed_amt = brokerage.get("commission_fixed_amount")
        perc = brokerage.get("commission_percentage")
        fixed_dec = Decimal(str(fixed_amt)) if fixed_amt is not None else None
        perc_dec = Decimal(str(perc)) if perc is not None else None
        if comm_type == BrokerageCommissionType.NONE:
            if fixed_amt or perc:
                raise PropertySubmissionError("No-fee deals cannot carry commission terms.")
        elif comm_type == BrokerageCommissionType.FIXED:
            if not fixed_dec or fixed_dec <= 0 or perc:
                raise PropertySubmissionError("A fixed-fee deal requires one positive fixed amount.")
        elif comm_type == BrokerageCommissionType.PERCENTAGE and (
            not perc_dec or not (Decimal("0") < perc_dec <= Decimal("100")) or fixed_amt
        ):
            raise PropertySubmissionError("A percentage commission must be > 0 and <= 100.")

        created_files_to_cleanup: list[PropertyPhoto] = []

        try:
            with transaction.atomic():
                prop_name = data.get("name") or f"{data.get('rooms')}-room property in {district.name}"
                prop_desc = data.get("description", "")
                prop = Property.objects.create(
                    name=prop_name,
                    name_en=prop_name,
                    name_uz=prop_name,
                    name_ru=prop_name,
                    address=data.get("address") or district.name,
                    district=district,
                    property_type=data.get("property_type", PropertyType.APARTMENT),
                    rooms=data.get("rooms"),
                    area_sqm=data.get("area_sqm"),
                    floor=floor,
                    total_floors=total_floors,
                    furnishing=data.get("furnishing", FurnishingType.UNFURNISHED),
                    owner=None,
                    engagement_type=PropertyEngagementType.ONE_OFF,
                    status=PropertyStatus.VACANT,
                    description=prop_desc,
                    description_en=prop_desc,
                    description_uz=prop_desc,
                    description_ru=prop_desc,
                    tariff=data.get("tariff", TariffChoices.STANDARD),
                    map_lat=data.get("map_lat"),
                    map_lon=data.get("map_lon"),
                    ask_price=ask_price,
                    ask_currency=data.get("ask_currency", "USD"),
                    deposit_amount=data.get("deposit_amount", Decimal("0.00")),
                    deposit_currency=data.get("deposit_currency", "USD"),
                    vacant_since=timezone.now().date(),
                    vacant_days=0,
                )

                if "translations" in data and isinstance(data["translations"], dict):
                    from core.services.localization import LocalizedContentService

                    LocalizedContentService().apply_translations(prop, data["translations"], ["name", "description"])
                    prop.save()

                amenity_slugs = data.get("amenities") or []
                if amenity_slugs:
                    prop.amenities.set(Amenity.objects.filter(slug__in=amenity_slugs, is_active=True))

                OneOffDeal.objects.create(
                    property=prop,
                    seller_name=brokerage.get("seller_name", ""),
                    seller_phone=brokerage.get("seller_phone", ""),
                    seller_email=brokerage.get("seller_email"),
                    channel=channel,
                    status=OneOffDealStatus.ACTIVE,
                    commission_type=comm_type,
                    commission_fixed_amount=fixed_dec,
                    commission_percentage=perc_dec,
                    commission_currency=brokerage.get("commission_currency", Currency.USD),
                )

                if is_marketplace:
                    Listing.objects.update_or_create(
                        property=prop,
                        defaults={
                            "status": ListingStatus.PUBLISHED,
                            "is_active": True,
                            "description": prop.description,
                            "description_en": getattr(prop, "description_en", prop.description),
                            "description_uz": getattr(prop, "description_uz", prop.description),
                            "description_ru": getattr(prop, "description_ru", prop.description),
                            "monthly_price": prop.ask_price,
                            "listed_price": prop.ask_price,
                            "deposit_amount": prop.deposit_amount,
                            "currency": prop.ask_currency,
                            "minimum_stay": data.get("minimum_stay", 6),
                            "price_includes": data.get("price_includes", []),
                            "published_at": timezone.now(),
                        },
                    )

                captions = data.get("captions") or []
                for idx, file_obj in enumerate(files):
                    photo = PropertyPhoto(
                        property=prop,
                        image=file_obj,
                        caption=captions[idx] if idx < len(captions) and captions[idx] else "",
                        is_primary=(idx == 0),
                        sort_order=idx,
                    )
                    photo.save()
                    created_files_to_cleanup.append(photo)

        except Exception as err:
            for photo in created_files_to_cleanup:
                try:
                    if photo.image:
                        photo.image.delete(save=False)
                    if photo.preview_image:
                        photo.preview_image.delete(save=False)
                    if photo.display_image:
                        photo.display_image.delete(save=False)
                except Exception:
                    pass
            raise err

        return prop

    @staticmethod
    def submit_owner_listing(
        *,
        user: User,
        data: dict[str, Any],
        files: list[UploadedFile],
    ) -> Listing:
        validate_images(files, min_photos=5, max_photos=12)

        if not data.get("accept_offer"):
            raise PropertySubmissionError("You must accept the public offer to submit a property.")

        district_id = data.get("district_id")
        district = District.objects.filter(pk=district_id, deleted_at__isnull=True).first()
        if not district:
            raise PropertySubmissionError("District not found.")

        floor = data.get("floor")
        total_floors = data.get("total_floors")
        validate_floor_bounds(floor, total_floors)

        monthly_price = data.get("monthly_price")
        if monthly_price is None or Decimal(str(monthly_price)) < 0:
            raise PropertySubmissionError("Monthly price is required and must be non-negative.")

        raw_deposit = data.get("deposit_amount")
        deposit_amount = Decimal(str(raw_deposit)) if raw_deposit is not None else Decimal("0.00")
        currency = data.get("currency", "USD")

        # Contact profile updates
        contact = data.get("contact")
        if contact:
            if contact.get("first_name"):
                user.first_name = contact["first_name"]
            if contact.get("last_name"):
                user.last_name = contact["last_name"]
            if contact.get("email"):
                user.email = contact["email"]
            if contact.get("phone"):
                user.phone = contact["phone"]

        if user.role != UserRole.OWNER and not user.is_staff and not user.is_superuser:
            user.role = UserRole.OWNER
        user.save()

        content_locale = data.get("content_locale") or "en"
        created_files_to_cleanup: list[PropertyPhoto] = []

        try:
            with transaction.atomic():
                prop_name = (
                    data.get("name")
                    or f"{data.get('rooms')}-room {str(data.get('property_type')).replace('_', ' ').title()} in {district.name}"
                )
                prop_desc = data.get("description", "")
                prop = Property.objects.create(
                    name=prop_name,
                    address=data.get("address") or district.name,
                    district=district,
                    property_type=data.get("property_type", PropertyType.APARTMENT),
                    rooms=data.get("rooms"),
                    area_sqm=data.get("area_sqm"),
                    floor=floor,
                    total_floors=total_floors,
                    furnishing=data.get("furnishing", FurnishingType.UNFURNISHED),
                    owner=user,
                    engagement_type=PropertyEngagementType.MANAGED,
                    status=PropertyStatus.PENDING_REVIEW,
                    description=prop_desc,
                    tariff=data.get("tariff", TariffChoices.STANDARD),
                    ask_price=monthly_price,
                    ask_currency=currency,
                    owner_guaranteed_price=monthly_price,
                    owner_guaranteed_currency=currency,
                    tenant_charge_price=monthly_price,
                    tenant_charge_currency=currency,
                    deposit_amount=deposit_amount,
                    deposit_currency=currency,
                )
                setattr(prop, f"name_{content_locale}", prop_name)
                setattr(prop, f"description_{content_locale}", prop_desc)
                prop.save(update_fields=[f"name_{content_locale}", f"description_{content_locale}"])

                amenity_slugs = data.get("amenities") or []
                if amenity_slugs:
                    prop.amenities.set(Amenity.objects.filter(slug__in=amenity_slugs, is_active=True))

                listing = Listing.objects.create(
                    property=prop,
                    status=ListingStatus.PENDING_REVIEW,
                    is_active=False,
                    description=prop_desc,
                    monthly_price=monthly_price,
                    listed_price=monthly_price,
                    deposit_amount=deposit_amount,
                    currency=currency,
                    minimum_stay=data.get("minimum_stay", 6),
                    price_includes=data.get("price_includes", []),
                    submitted_at=timezone.now(),
                )
                setattr(listing, f"description_{content_locale}", prop_desc)
                listing.save(update_fields=[f"description_{content_locale}"])

                active_offer = PublicOffer.get_active()
                onboarding = OwnerOnboarding(owner=user, property=prop)
                if active_offer:
                    onboarding.accept_offer(active_offer, locale=content_locale)
                onboarding.save()

                captions = data.get("captions") or []
                for idx, file_obj in enumerate(files):
                    cap = captions[idx] if idx < len(captions) and captions[idx] else ""
                    photo = PropertyPhoto(
                        property=prop,
                        image=file_obj,
                        caption=cap,
                        is_primary=(idx == 0),
                        sort_order=idx,
                    )
                    setattr(photo, f"caption_{content_locale}", cap)
                    photo.save()
                    created_files_to_cleanup.append(photo)

        except Exception as err:
            for photo in created_files_to_cleanup:
                try:
                    if photo.image:
                        photo.image.delete(save=False)
                    if photo.preview_image:
                        photo.preview_image.delete(save=False)
                    if photo.display_image:
                        photo.display_image.delete(save=False)
                except Exception:
                    pass
            raise err

        return listing

    @staticmethod
    def resubmit_rejected_listing(
        *,
        user: User,
        listing: Listing,
        data: dict[str, Any],
        files: list[UploadedFile],
    ) -> Listing:
        if listing.status != ListingStatus.REJECTED:
            raise PropertySubmissionError("Only rejected listings can be resubmitted.")

        prop = listing.property
        if prop.owner_id != user.id and not (user.is_staff or user.is_superuser):
            raise PropertySubmissionError("You do not own this listing.")

        keep_photo_ids = []
        for pid in data.get("keep_photo_ids", []):
            try:
                keep_photo_ids.append(int(pid))
            except ValueError, TypeError:
                continue
        existing_photos_qs = prop.photos.filter(id__in=keep_photo_ids)
        kept_photos_count = existing_photos_qs.count()
        total_photos_count = kept_photos_count + len(files)

        if total_photos_count < 5:
            raise PropertySubmissionError(f"At least 5 photos are required (found {total_photos_count}).")
        if total_photos_count > 12:
            raise PropertySubmissionError(f"At most 12 photos are allowed (found {total_photos_count}).")

        for f in files:
            validate_image_file(f)

        district_id = data.get("district_id", prop.district_id)
        district = District.objects.filter(pk=district_id, deleted_at__isnull=True).first()
        if not district:
            raise PropertySubmissionError("District not found.")

        floor = data.get("floor", prop.floor)
        total_floors = data.get("total_floors", prop.total_floors)
        validate_floor_bounds(floor, total_floors)

        monthly_price = data.get("monthly_price", listing.monthly_price)
        if monthly_price is None or Decimal(str(monthly_price)) < 0:
            raise PropertySubmissionError("Monthly price must be non-negative.")

        deposit_amount = data.get("deposit_amount", listing.deposit_amount or Decimal("0.00"))
        currency = data.get("currency", listing.currency or "USD")

        new_photos_created: list[PropertyPhoto] = []

        try:
            with transaction.atomic():
                # Delete photos not kept
                unkept_photos = prop.photos.exclude(id__in=keep_photo_ids)
                for unkept in unkept_photos:
                    if unkept.image:
                        unkept.image.delete(save=False)
                    if unkept.preview_image:
                        unkept.preview_image.delete(save=False)
                    if unkept.display_image:
                        unkept.display_image.delete(save=False)
                    unkept.delete()

                # Update property metadata
                prop.name = data.get("name") or prop.name
                prop.address = data.get("address") or prop.address or (district.name if district else "")
                prop.district = district
                prop.property_type = data.get("property_type") or prop.property_type
                prop.rooms = data.get("rooms") or prop.rooms
                prop.area_sqm = data.get("area_sqm") or prop.area_sqm
                prop.floor = floor
                prop.total_floors = total_floors
                prop.furnishing = data.get("furnishing") or prop.furnishing
                prop.description = data.get("description") or prop.description
                prop.tariff = data.get("tariff") or prop.tariff
                prop.ask_price = monthly_price
                prop.ask_currency = currency
                prop.owner_guaranteed_price = monthly_price
                prop.owner_guaranteed_currency = currency
                prop.tenant_charge_price = monthly_price
                prop.tenant_charge_currency = currency
                prop.deposit_amount = deposit_amount
                prop.deposit_currency = currency
                prop.status = PropertyStatus.PENDING_REVIEW
                prop.save()

                if "amenities" in data and data["amenities"] is not None:
                    prop.amenities.set(Amenity.objects.filter(slug__in=data["amenities"], is_active=True))

                # Re-index kept photos
                kept_photos = list(prop.photos.order_by("sort_order", "id"))
                for idx, photo in enumerate(kept_photos):
                    photo.sort_order = idx
                    photo.is_primary = idx == 0
                    photo.save(update_fields=["sort_order", "is_primary", "updated_at"])

                # Add new photos
                captions = data.get("captions") or []
                start_sort = len(kept_photos)
                for idx, file_obj in enumerate(files):
                    photo = PropertyPhoto(
                        property=prop,
                        image=file_obj,
                        caption=captions[idx] if idx < len(captions) and captions[idx] else "",
                        is_primary=(start_sort == 0 and idx == 0),
                        sort_order=start_sort + idx,
                    )
                    photo.save()
                    new_photos_created.append(photo)

                # Update listing
                listing.status = ListingStatus.PENDING_REVIEW
                listing.is_active = False
                listing.description = prop.description
                listing.monthly_price = monthly_price
                listing.listed_price = monthly_price
                listing.deposit_amount = deposit_amount
                listing.currency = currency
                if "minimum_stay" in data:
                    listing.minimum_stay = data["minimum_stay"]
                if "price_includes" in data and data["price_includes"] is not None:
                    listing.price_includes = [slug for slug in data["price_includes"] if slug in PriceIncluded.values()]
                listing.rejection_reason = None
                listing.submitted_at = timezone.now()
                listing.save()
                prop.refresh_from_db()
                listing.refresh_from_db()

        except Exception as err:
            for photo in new_photos_created:
                try:
                    if photo.image:
                        photo.image.delete(save=False)
                    if photo.preview_image:
                        photo.preview_image.delete(save=False)
                    if photo.display_image:
                        photo.display_image.delete(save=False)
                except Exception:
                    pass
            raise err

        return listing
