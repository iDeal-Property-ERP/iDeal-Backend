from http import HTTPStatus
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from dmr.pagination import Paginated
from property.models import OneOffDeal, Property, VerificationVisit
from property.services.validation import validate_floor_bounds

from api.v1.property.schemas import (
    OneOffPropertyDraftInput,
    OneOffPropertyUpdateInput,
    PropertyCreateInput,
    PropertyDraftCreateInput,
    PropertyOutput,
    PropertyPhotoReorderInput,
    PropertyPublishInput,
    PropertyUpdateInput,
    VerificationVisitCreateInput,
)
from core.api.permissions import require_role
from core.api.schemas import DeleteData
from core.api.views import (
    CreateAPIView,
    DeleteAPIView,
    DetailPath,
    GenericController,
    ListAPIView,
    ListQuery,
    PartialUpdateAPIView,
    RetrieveAPIView,
)
from core.constants import OneOffDealStatus, PropertyEngagementType, PropertyStatus, UserRole, VerificationVisitStatus

# Fields that must be present before a draft can be published (go VACANT).
PUBLISH_REQUIRED_FIELDS = (
    "district",
    "owner",
    "rooms",
    "area_sqm",
    "floor",
    "total_floors",
    "ask_price",
    "owner_guaranteed_price",
    "tenant_charge_price",
)
MIN_PUBLISH_PHOTOS = 5


def _photo_url(photo, request):
    url = photo.image.url
    return request.build_absolute_uri(url) if request is not None else url


def _property_output(prop, request) -> dict:
    """Build the property output dict, injecting absolute photo URLs and the
    next scheduled verification visit (the generic reverse managers cannot be
    validated straight through pydantic)."""
    photos = [
        {
            "id": p.id,
            "image_url": _photo_url(p, request),
            "caption": p.caption or None,
            "is_primary": p.is_primary,
            "sort_order": p.sort_order,
        }
        for p in sorted(prop.photos.all(), key=lambda p: (not p.is_primary, p.sort_order))
    ]
    next_visit = (
        prop.verification_visits.filter(status=VerificationVisitStatus.SCHEDULED).order_by("scheduled_for").first()
    )
    data = PropertyOutput.model_validate(prop).model_dump(mode="json")
    data["engagement_type"] = prop.engagement_type
    if prop.engagement_type == PropertyEngagementType.ONE_OFF:
        try:
            deal = prop.one_off_deal
            data["one_off_deal"] = {
                "id": deal.id,
                "seller_name": deal.seller_name,
                "seller_phone": deal.seller_phone,
                "seller_email": deal.seller_email,
                "channel": deal.channel,
                "status": deal.status,
                "commission_type": deal.commission_type,
                "commission_fixed_amount": deal.commission_fixed_amount,
                "commission_percentage": deal.commission_percentage,
                "commission_currency": deal.commission_currency,
                "close_date": deal.close_date,
                "receipt_recorded": hasattr(deal, "receipt"),
            }
        except OneOffDeal.DoesNotExist:
            data["one_off_deal"] = None
    data["photos"] = photos
    if prop.engagement_type != PropertyEngagementType.ONE_OFF and next_visit is not None:
        data["verification"] = {
            "id": next_visit.id,
            "scheduled_for": next_visit.scheduled_for.isoformat(),
            "status": next_visit.status,
            "completed_at": next_visit.completed_at.isoformat() if next_visit.completed_at else None,
            "notes": next_visit.notes,
        }
    else:
        data["verification"] = None
    return data


def _base_property_qs(user):
    qs = Property.objects.select_related("district", "owner", "one_off_deal").prefetch_related(
        "photos", "verification_visits"
    )
    if user.role == UserRole.OWNER:
        # Owners never see draft properties (not yet published under management).
        return qs.filter(owner=user).exclude(status=PropertyStatus.DRAFT)
    return qs.all()


class PropertyListCreateView(CreateAPIView, ListAPIView):
    model = Property
    output_schema = PropertyOutput
    create_schema = PropertyCreateInput
    update_schema = PropertyUpdateInput

    def get_queryset(self):
        return _base_property_qs(self.request.user)

    def to_output(self, instance):
        return _property_output(instance, self.request)

    @require_role(UserRole.MANAGEMENT)
    def post(self, parsed_body: Body[PropertyCreateInput]) -> PropertyOutput:
        return super().post(parsed_body)

    @require_role(UserRole.MANAGEMENT, UserRole.OWNER)
    def get(self, parsed_query: Query[ListQuery]) -> list[PropertyOutput] | Paginated[PropertyOutput]:
        return super().get(parsed_query)


class PropertyDetailView(RetrieveAPIView, PartialUpdateAPIView, DeleteAPIView):
    model = Property
    output_schema = PropertyOutput
    create_schema = PropertyCreateInput
    update_schema = PropertyUpdateInput

    def get_queryset(self):
        return _base_property_qs(self.request.user)

    def to_output(self, instance):
        return _property_output(instance, self.request)

    def perform_update(self, instance, validated_data):
        try:
            validate_floor_bounds(
                validated_data.get("floor", instance.floor),
                validated_data.get("total_floors", instance.total_floors),
            )
        except ValueError as err:
            return self.fail(error=str(err), message=str(_("Validation error")))
        return super().perform_update(instance, validated_data)

    @require_role(UserRole.MANAGEMENT, UserRole.OWNER)
    def get(self, parsed_path: Path[DetailPath]) -> PropertyOutput:
        return super().get(parsed_path)

    @require_role(UserRole.MANAGEMENT)
    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[PropertyUpdateInput]) -> PropertyOutput:
        prop = self.get_object(pk=parsed_path.pk)
        if prop.engagement_type == PropertyEngagementType.ONE_OFF:
            try:
                locked = prop.one_off_deal.status in {
                    OneOffDealStatus.CLOSED_WON,
                    OneOffDealStatus.CLOSED_LOST,
                    OneOffDealStatus.ARCHIVED,
                }
            except Exception:
                locked = False
            if locked:
                changed = set(parsed_body.model_dump(exclude_unset=True))
                if changed - ONE_OFF_CLOSED_EDITABLE_FIELDS:
                    return self.fail(error=str(_("Closed one-off commercial terms are read-only")))
        return super().patch(parsed_path, parsed_body)

    @require_role(UserRole.MANAGEMENT)
    def delete(self, parsed_path: Path[DetailPath]) -> DeleteData:
        prop = self.get_object(pk=parsed_path.pk)
        # A property archive must preserve agreements, leases, and their history.
        # django-softdelete recursively walks reverse relations and raises on their
        # PROTECT foreign keys, even though this endpoint is only a soft delete.
        # Update the property row directly so it disappears from active queries
        # without deleting or altering any related business records.
        Property.global_objects.filter(pk=prop.pk).update(
            deleted_at=timezone.now(),
            restored_at=None,
            transaction_id=uuid4(),
        )
        return self.ok({"deleted": True})


class PropertyDraftCreateView(CreateAPIView):
    model = Property
    output_schema = PropertyOutput
    create_schema = PropertyDraftCreateInput

    def to_output(self, instance):
        return _property_output(instance, self.request)

    def perform_create(self, validated_data):
        # Drafts save only the fields the user has touched; None values fall back
        # to model defaults (e.g. score, vacant_days) instead of violating NOT NULL.
        data = {k: v for k, v in validated_data.items() if v is not None}
        data["status"] = PropertyStatus.DRAFT
        return Property.objects.create(**data)

    @require_role(UserRole.MANAGEMENT)
    def post(self, parsed_body: Body[PropertyDraftCreateInput]) -> PropertyOutput:
        return super().post(parsed_body)


ONE_OFF_MANAGED_ONLY_FIELDS = {
    "owner_id",
    "owner_guaranteed_price",
    "owner_guaranteed_currency",
    "tenant_charge_price",
    "tenant_charge_currency",
}
ONE_OFF_DISALLOWED_FIELDS = ONE_OFF_MANAGED_ONLY_FIELDS | {
    "status",
    "score",
    "vacant_since",
    "vacant_days",
}
ONE_OFF_CLOSED_EDITABLE_FIELDS = {
    "name",
    "address",
    "district_id",
    "rooms",
    "area_sqm",
    "floor",
    "total_floors",
    "map_lat",
    "map_lon",
    "description",
    "tariff",
}


def _apply_one_off_property_data(prop, data):
    for field, value in data.items():
        if field in ONE_OFF_DISALLOWED_FIELDS:
            raise ValueError("Managed-only or lifecycle fields are not available for one-off properties")
        setattr(prop, field, value)


class OneOffPropertyDraftView(GenericController):
    """Creates a draft property and its draft brokerage deal in one transaction."""

    output_schema = PropertyOutput

    @require_role(UserRole.MANAGEMENT)
    def post(self, parsed_body: Body[OneOffPropertyDraftInput]) -> PropertyOutput:
        data = parsed_body.model_dump(exclude_unset=True)
        brokerage = data.pop("brokerage", {})
        if set(data) & ONE_OFF_DISALLOWED_FIELDS:
            return self.fail(error=str(_("Managed-only or lifecycle fields are not available for one-off properties")))
        try:
            with transaction.atomic():
                prop = Property.objects.create(
                    name=data.pop("name", "Untitled property"),
                    status=PropertyStatus.DRAFT,
                    engagement_type=PropertyEngagementType.ONE_OFF,
                    **data,
                )
                OneOffDeal.objects.create(property=prop, **brokerage)
        except (ValidationError, ValueError) as err:
            return self.fail(error=str(err), message=str(_("Validation error")))
        return self.ok(_property_output(prop, self.request), status_code=HTTPStatus.CREATED)


class OneOffPropertyUpdateView(GenericController):
    """Atomically updates a one-off property and draft brokerage terms."""

    output_schema = PropertyOutput

    def get_queryset(self):
        return _base_property_qs(self.request.user).filter(engagement_type=PropertyEngagementType.ONE_OFF)

    @require_role(UserRole.MANAGEMENT)
    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[OneOffPropertyUpdateInput]) -> PropertyOutput:
        prop = self.get_object(pk=parsed_path.pk)
        data = parsed_body.model_dump(exclude_unset=True)
        brokerage = data.pop("brokerage", None)
        deal = prop.one_off_deal
        if set(data) & ONE_OFF_DISALLOWED_FIELDS:
            return self.fail(error=str(_("Managed-only or lifecycle fields are not available for one-off properties")))
        closed = deal.status in {
            OneOffDealStatus.CLOSED_WON,
            OneOffDealStatus.CLOSED_LOST,
            OneOffDealStatus.ARCHIVED,
        }
        if closed and (brokerage is not None or set(data) - ONE_OFF_CLOSED_EDITABLE_FIELDS):
            return self.fail(error=str(_("Closed one-off commercial terms are read-only")))
        try:
            with transaction.atomic():
                _apply_one_off_property_data(prop, data)
                validate_floor_bounds(prop.floor, prop.total_floors)
                prop.save()
                if brokerage is not None:
                    for field, value in brokerage.items():
                        setattr(deal, field, value)
                    deal.save()
        except (ValidationError, ValueError) as err:
            return self.fail(error=str(err), message=str(_("Validation error")))
        return self.ok(_property_output(prop, self.request))


class ManagementPropertyView(GenericController):
    output_schema = PropertyOutput

    def get_queryset(self):
        # No prefetch: these are single-object views that mutate photos/visits,
        # so the output builder must read fresh relations, not a stale cache.
        return Property.objects.select_related("district", "owner")

    def to_output(self, instance):
        return _property_output(instance, self.request)

    def ensure_mutable(self, prop, *, allow_closed_metadata=False):
        if prop.engagement_type != PropertyEngagementType.ONE_OFF:
            return
        try:
            status = prop.one_off_deal.status
        except Exception:
            return
        if not allow_closed_metadata and status in {
            OneOffDealStatus.CLOSED_WON,
            OneOffDealStatus.CLOSED_LOST,
            OneOffDealStatus.ARCHIVED,
        }:
            self.fail(error=str(_("Closed one-off brokerage properties are read-only")))


class PropertyPublishView(ManagementPropertyView):
    @require_role(UserRole.MANAGEMENT)
    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[PropertyPublishInput]) -> dict:
        prop = self.get_object(pk=parsed_path.pk)
        self.ensure_mutable(prop)
        if prop.status != PropertyStatus.DRAFT:
            return self.fail(
                error=str(_("Only draft properties can be published")),
                message=str(_("Invalid status transition")),
            )
        missing = [
            field
            for field in PUBLISH_REQUIRED_FIELDS
            if getattr(prop, f"{field}_id", getattr(prop, field, None)) is None
        ]
        # address is blank="" (not null) on a draft — treat empty as missing.
        if not (prop.address or "").strip():
            missing.insert(0, "address")
        if prop.photos.count() < MIN_PUBLISH_PHOTOS:
            missing.append("photos")
        if missing:
            return self.fail(
                error={"code": "incomplete", "missing": missing},
                message=str(_("Property is not ready to publish")),
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        with transaction.atomic():
            prop.status = PropertyStatus.VACANT
            prop.vacant_since = timezone.now().date()
            prop.vacant_days = 0
            prop.save(update_fields=["status", "vacant_since", "vacant_days", "updated_at"])
            if (
                parsed_body.schedule_verification_at is not None
                and prop.engagement_type != PropertyEngagementType.ONE_OFF
            ):
                VerificationVisit.objects.create(
                    property=prop,
                    scheduled_for=parsed_body.schedule_verification_at,
                    scheduled_by=self.request.user,
                )
        return self.ok(self.to_output(prop), status_code=HTTPStatus.OK)


class PropertyPhotosView(ManagementPropertyView):
    @require_role(UserRole.MANAGEMENT)
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        from property.models import PropertyPhoto

        from core.utils.uploads import UploadError, save_uploaded_images

        prop = self.get_object(pk=parsed_path.pk)
        self.ensure_mutable(prop, allow_closed_metadata=True)
        files = self.request.FILES.getlist("images")
        if not files:
            return self.fail(error=str(_("No images provided")))
        existing = prop.photos.count()
        try:
            created = save_uploaded_images(PropertyPhoto, "property", prop, files)
        except UploadError as err:
            return self.fail(error=str(err))
        for idx, photo in enumerate(created):
            photo.sort_order = existing + idx
            photo.is_primary = existing == 0 and idx == 0
            photo.save(update_fields=["sort_order", "is_primary", "updated_at"])
        return self.ok(self.to_output(prop), status_code=HTTPStatus.CREATED)


class PropertyPhotoReorderView(ManagementPropertyView):
    @require_role(UserRole.MANAGEMENT)
    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[PropertyPhotoReorderInput]) -> dict:
        prop = self.get_object(pk=parsed_path.pk)
        self.ensure_mutable(prop, allow_closed_metadata=True)
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
        prop.refresh_from_db()
        return self.ok(self.to_output(prop))


class PropertyPhotoPath(DetailPath):
    photo_id: int


class PropertyPhotoDeleteView(ManagementPropertyView):
    @require_role(UserRole.MANAGEMENT)
    def delete(self, parsed_path: Path[PropertyPhotoPath]) -> dict:
        prop = self.get_object(pk=parsed_path.pk)
        self.ensure_mutable(prop, allow_closed_metadata=True)
        photo = prop.photos.filter(pk=parsed_path.photo_id).first()
        if photo is None:
            return self.fail(error=str(_("Photo not found")), status_code=HTTPStatus.NOT_FOUND)
        was_primary = photo.is_primary
        photo.delete()
        # Never leave a property with photos but no cover — promote the next one.
        if was_primary:
            successor = prop.photos.order_by("sort_order", "id").first()
            if successor is not None:
                successor.is_primary = True
                successor.save(update_fields=["is_primary", "updated_at"])
        return self.ok(self.to_output(prop))


class PropertyVerificationVisitView(ManagementPropertyView):
    @require_role(UserRole.MANAGEMENT)
    def get(self, parsed_path: Path[DetailPath]) -> dict:
        prop = self.get_object(pk=parsed_path.pk)
        visits = [
            {
                "id": v.id,
                "scheduled_for": v.scheduled_for.isoformat(),
                "status": v.status,
                "completed_at": v.completed_at.isoformat() if v.completed_at else None,
                "notes": v.notes,
            }
            for v in prop.verification_visits.all()
        ]
        return self.ok(visits)

    @require_role(UserRole.MANAGEMENT)
    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[VerificationVisitCreateInput]) -> dict:
        prop = self.get_object(pk=parsed_path.pk)
        if prop.engagement_type == PropertyEngagementType.ONE_OFF:
            return self.fail(error=str(_("Verification visits are only for managed properties")))
        self.ensure_mutable(prop)
        visit = VerificationVisit.objects.create(
            property=prop,
            scheduled_for=parsed_body.scheduled_for,
            notes=parsed_body.notes,
            scheduled_by=self.request.user,
        )
        return self.ok(
            {
                "id": visit.id,
                "scheduled_for": visit.scheduled_for.isoformat(),
                "status": visit.status,
                "completed_at": None,
                "notes": visit.notes,
            },
            status_code=HTTPStatus.CREATED,
        )
