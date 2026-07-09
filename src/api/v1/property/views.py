from http import HTTPStatus

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from dmr.pagination import Paginated
from property.models import Property, VerificationVisit

from api.v1.property.schemas import (
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
from core.constants import PropertyStatus, UserRole, VerificationVisitStatus

# Fields that must be present before a draft can be published (go VACANT).
PUBLISH_REQUIRED_FIELDS = (
    "district",
    "owner",
    "rooms",
    "area_sqm",
    "floor",
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
    data["photos"] = photos
    if next_visit is not None:
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
    qs = Property.objects.select_related("district", "owner").prefetch_related("photos", "verification_visits")
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

    @require_role(UserRole.MANAGEMENT, UserRole.OWNER)
    def get(self, parsed_path: Path[DetailPath]) -> PropertyOutput:
        return super().get(parsed_path)

    @require_role(UserRole.MANAGEMENT)
    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[PropertyUpdateInput]) -> PropertyOutput:
        return super().patch(parsed_path, parsed_body)

    @require_role(UserRole.MANAGEMENT)
    def delete(self, parsed_path: Path[DetailPath]) -> DeleteData:
        return super().delete(parsed_path)


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


class ManagementPropertyView(GenericController):
    output_schema = PropertyOutput

    def get_queryset(self):
        # No prefetch: these are single-object views that mutate photos/visits,
        # so the output builder must read fresh relations, not a stale cache.
        return Property.objects.select_related("district", "owner")

    def to_output(self, instance):
        return _property_output(instance, self.request)


class PropertyPublishView(ManagementPropertyView):
    @require_role(UserRole.MANAGEMENT)
    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[PropertyPublishInput]) -> dict:
        prop = self.get_object(pk=parsed_path.pk)
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
            if parsed_body.schedule_verification_at is not None:
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
