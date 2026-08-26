import json
from http import HTTPStatus

import pydantic
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from dmr.pagination import Paginated
from inventory.models import InventoryAct
from inventory.services.submission import InventorySubmissionError, InventorySubmissionService

from api.v1.inventory.schemas import (
    InventoryActAcknowledgeInput,
    InventoryActListOutput,
    InventoryActOutput,
    InventoryActSubmitPayload,
)
from core.api.permissions import RoleAuth
from core.api.views import BaseController, DetailPath, GenericController
from core.constants import InventoryActStatus, UserRole
from core.utils.pagination import build_paginated_response


class InventoryActFilterQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20
    property_id: int | None = None
    lease_id: int | None = None
    status: str | None = None
    awaiting_ack: bool | None = None


def _awaiting_ack_q():
    """Finalized acts the counterparty has not acknowledged yet."""
    from django.db.models import Q

    return Q(status=InventoryActStatus.FINALIZED, acknowledged_at__isnull=True)


class InventoryActListCreateView(GenericController):
    model = InventoryAct
    output_schema = InventoryActListOutput
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
        if parsed_query.awaiting_ack:
            qs = qs.filter(_awaiting_ack_q())
        items = [InventoryActListOutput.model_validate(obj).model_dump(mode="json") for obj in qs]
        if parsed_query.page is not None:
            return self.ok(build_paginated_response(items, parsed_query.page, parsed_query.per_page))
        return self.ok(items)

    def post(self) -> dict:
        payload_raw = self.request.POST.get("payload")
        if not payload_raw:
            return self.fail(error=str(_("Missing payload data")))

        payload_str = str(payload_raw) if not isinstance(payload_raw, str) else payload_raw

        try:
            data = json.loads(payload_str)
            validated = InventoryActSubmitPayload.model_validate(data)
        except (json.JSONDecodeError, pydantic.ValidationError) as err:
            return self.fail(error=str(err), message=str(_("Invalid payload")))

        raw_files = self.request.FILES.getlist("images") if hasattr(self.request, "FILES") else []
        files = list(raw_files) if isinstance(raw_files, (list, tuple)) else []

        try:
            act = InventorySubmissionService.submit_act(
                user=self.request.user,
                data=validated.model_dump(mode="json"),
                files=files,
            )
        except InventorySubmissionError as err:
            return self.fail(error=str(err), status_code=HTTPStatus.UNPROCESSABLE_ENTITY)
        except Exception as err:
            return self.fail(error=str(err), message=str(_("Failed to submit inventory act")))

        return self.ok(InventoryActOutput.model_validate(act).model_dump(mode="json"), status_code=HTTPStatus.CREATED)


class InventoryActStatsView(BaseController):
    """Saved-view counts for the Inventory acts workbench."""

    auth = (RoleAuth(UserRole.MANAGEMENT, UserRole.AGENT),)

    def get(self) -> dict:
        base = InventoryAct.objects.all()
        return self.ok(
            {
                "counts": {
                    "finalized": base.filter(status=InventoryActStatus.FINALIZED).count(),
                    "awaiting_ack": base.filter(_awaiting_ack_q()).count(),
                    "all": base.count(),
                }
            }
        )


class InventoryActDetailView(GenericController):
    """Detail view. Management/agent always; tenant only on their lease."""

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


class InventoryActAcknowledgeView(GenericController):
    model = InventoryAct
    output_schema = InventoryActOutput

    def get_queryset(self):
        return InventoryAct.objects.select_related("property", "lease").prefetch_related("items", "photos").all()

    def post(
        self, parsed_path: Path[DetailPath], parsed_body: Body[InventoryActAcknowledgeInput]
    ) -> InventoryActOutput:
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

        with transaction.atomic():
            act = InventoryAct.objects.select_for_update().get(pk=act.pk)
            if act.acknowledged_at is not None:
                return self.fail(
                    error={"code": "inventory_act_already_acknowledged"},
                    message=str(_("Inventory act has already been acknowledged")),
                    status_code=HTTPStatus.CONFLICT,
                )

            act.acknowledged_by_name = parsed_body.acknowledged_by_name
            act.acknowledged_at = timezone.now()
            if parsed_body.acknowledgment_note is not None:
                act.acknowledgment_note = parsed_body.acknowledgment_note
            act.save(update_fields=["acknowledged_by_name", "acknowledged_at", "acknowledgment_note", "updated_at"])

        return self.ok(InventoryActOutput.model_validate(act).model_dump(mode="json"), status_code=HTTPStatus.OK)
