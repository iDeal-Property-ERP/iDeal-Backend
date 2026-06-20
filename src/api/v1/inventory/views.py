from http import HTTPStatus

import pydantic
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from dmr.pagination import Paginated
from inventory.models import InventoryAct, InventoryActItem, InventoryActPhoto

from api.v1.inventory.schemas import (
    InventoryActCreateInput,
    InventoryActFinalizeInput,
    InventoryActItemsBulkInput,
    InventoryActListOutput,
    InventoryActOutput,
    InventoryActPhotoOutput,
    InventoryActUpdateInput,
)
from core.api.permissions import RoleAuth, require_role
from core.api.views import BaseController, DetailPath, GenericController
from core.constants import InventoryActStatus, UserRole
from core.utils.pagination import build_paginated_response
from core.utils.uploads import UploadError, save_uploaded_images


class InventoryActFilterQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20
    property_id: int | None = None
    lease_id: int | None = None
    status: str | None = None


class InventoryActListCreateView(GenericController):
    model = InventoryAct
    output_schema = InventoryActListOutput
    create_schema = InventoryActCreateInput
    auth = (RoleAuth(UserRole.MANAGEMENT, UserRole.AGENT),)

    def get_queryset(self):
        return InventoryAct.objects.select_related("property").prefetch_related("items", "photos")

    def get(
        self, parsed_query: Query[InventoryActFilterQuery]
    ) -> list[InventoryActListOutput] | Paginated[InventoryActListOutput]:
        qs = self.get_queryset()
        if parsed_query.property_id is not None:
            qs = qs.filter(property_id=parsed_query.property_id)
        if parsed_query.lease_id is not None:
            qs = qs.filter(lease_id=parsed_query.lease_id)
        if parsed_query.status is not None:
            qs = qs.filter(status=parsed_query.status)
        items = [InventoryActListOutput.model_validate(obj).model_dump(mode="json") for obj in qs]
        if parsed_query.page is not None:
            return self.ok(build_paginated_response(items, parsed_query.page, parsed_query.per_page))
        return self.ok(items)

    def post(self, parsed_body: Body[InventoryActCreateInput]) -> InventoryActOutput:
        data = parsed_body.model_dump()
        act = InventoryAct.objects.create(created_by=self.request.user, **data)
        return self.ok(InventoryActOutput.model_validate(act).model_dump(mode="json"))


class InventoryActDetailView(GenericController):
    """Detail + draft-only edit. Management/agent always; tenant only on their lease."""

    model = InventoryAct
    output_schema = InventoryActOutput

    def get_queryset(self):
        return InventoryAct.objects.select_related("property", "lease").prefetch_related("items", "photos").all()

    def get(self, parsed_path: Path[DetailPath]) -> InventoryActOutput:
        act = self.get_object(pk=parsed_path.pk)
        user = self.request.user
        if user.role == UserRole.TENANT:
            if act.lease_id is None or act.lease.tenant_id != user.id:
                return self.fail(
                    error=str(_("You do not have access to this inventory act")),
                    status_code=HTTPStatus.FORBIDDEN,
                )
        elif user.role not in (UserRole.MANAGEMENT, UserRole.AGENT):
            return self.fail(
                error=str(_("You do not have permission to access this endpoint")),
                status_code=HTTPStatus.FORBIDDEN,
            )
        return self.ok(InventoryActOutput.model_validate(act).model_dump(mode="json"))

    @require_role(UserRole.MANAGEMENT, UserRole.AGENT)
    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[InventoryActUpdateInput]) -> InventoryActOutput:
        act = self.get_object(pk=parsed_path.pk)
        if act.status != InventoryActStatus.DRAFT:
            return self.fail(
                error=str(_("Only draft acts can be edited")),
                message=str(_("Act is finalized")),
            )
        for attr, value in parsed_body.model_dump(exclude_unset=True).items():
            setattr(act, attr, value)
        act.save()
        return self.ok(InventoryActOutput.model_validate(act).model_dump(mode="json"))


class InventoryActItemsView(GenericController):
    model = InventoryAct
    auth = (RoleAuth(UserRole.MANAGEMENT, UserRole.AGENT),)

    def get_queryset(self):
        return InventoryAct.objects.prefetch_related("items", "photos").all()

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[InventoryActItemsBulkInput]) -> InventoryActOutput:
        act = self.get_object(pk=parsed_path.pk)
        if act.status != InventoryActStatus.DRAFT:
            return self.fail(
                error=str(_("Only draft acts can be edited")),
                message=str(_("Act is finalized")),
            )
        # Replace the act's items with the provided set.
        act.items.all().delete()
        InventoryActItem.objects.bulk_create(
            [
                InventoryActItem(
                    act=act,
                    area=item.area,
                    condition=item.condition,
                    notes=item.notes,
                    sort_order=item.sort_order,
                )
                for item in parsed_body.items
            ]
        )
        act.refresh_from_db()
        return self.ok(
            InventoryActOutput.model_validate(act).model_dump(mode="json"),
            status_code=HTTPStatus.OK,
        )


class InventoryActPhotosView(BaseController):
    """Multipart photo upload. Reads request.FILES directly (no Pydantic body)."""

    auth = (RoleAuth(UserRole.MANAGEMENT, UserRole.AGENT),)

    def post(self, parsed_path: Path[DetailPath]) -> dict:
        act = InventoryAct.objects.filter(pk=parsed_path.pk).first()
        if act is None:
            return self.fail(error=str(_("Inventory act not found")), status_code=HTTPStatus.NOT_FOUND)
        if act.status != InventoryActStatus.DRAFT:
            return self.fail(
                error=str(_("Only draft acts can be edited")),
                message=str(_("Act is finalized")),
            )

        files = self.request.FILES.getlist("images")
        if not files:
            return self.fail(error=str(_("No images provided")))

        item_id = self.request.POST.get("item_id")
        extra = {"item_id": int(item_id)} if item_id else {}
        try:
            created = save_uploaded_images(InventoryActPhoto, "act", act, files, extra=extra)
        except UploadError as err:
            return self.fail(error=str(err))

        data = [InventoryActPhotoOutput.model_validate(p).model_dump(mode="json") for p in created]
        return self.ok(data, status_code=HTTPStatus.CREATED)


class InventoryActFinalizeView(GenericController):
    model = InventoryAct
    auth = (RoleAuth(UserRole.MANAGEMENT, UserRole.AGENT),)

    def get_queryset(self):
        return InventoryAct.objects.prefetch_related("items", "photos").all()

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[InventoryActFinalizeInput]) -> InventoryActOutput:
        act = self.get_object(pk=parsed_path.pk)
        if act.status == InventoryActStatus.FINALIZED:
            return self.fail(
                error=str(_("Act is already finalized")),
                message=str(_("Invalid status transition")),
            )
        act.status = InventoryActStatus.FINALIZED
        act.finalized_at = timezone.now()
        if parsed_body.acknowledged_by_name:
            act.acknowledged_by_name = parsed_body.acknowledged_by_name
            act.acknowledged_at = timezone.now()
        act.acknowledgment_note = parsed_body.acknowledgment_note
        act.save(
            update_fields=[
                "status",
                "finalized_at",
                "acknowledged_by_name",
                "acknowledged_at",
                "acknowledgment_note",
                "updated_at",
            ]
        )
        return self.ok(
            InventoryActOutput.model_validate(act).model_dump(mode="json"),
            status_code=HTTPStatus.OK,
        )
