from http import HTTPStatus

import pydantic
from dmr import Body, Path, Query
from dmr.pagination import Paginated
from maintenance.models import ServiceRequest

from api.v1.maintenance.schemas import (
    ServiceRequestAssignInput,
    ServiceRequestCreateInput,
    ServiceRequestOutput,
    ServiceRequestResolveInput,
    ServiceRequestUpdateInput,
)
from core.api.permissions import RoleAuth
from core.api.views import CreateAPIView, DetailPath, GenericController, ListAPIView, RetrieveAPIView
from core.constants import ServiceRequestStatus, UserRole
from core.utils.pagination import build_paginated_response


class ServiceRequestFilterQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20
    status: str | None = None
    property_id: int | None = None


class ServiceRequestListCreateView(CreateAPIView, ListAPIView):
    model = ServiceRequest
    output_schema = ServiceRequestOutput
    create_schema = ServiceRequestCreateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return ServiceRequest.objects.select_related("property", "tenant", "assigned_to").all()

    def post(self, parsed_body: Body[ServiceRequestCreateInput]) -> ServiceRequestOutput:
        return super().post(parsed_body)

    def get(
        self, parsed_query: Query[ServiceRequestFilterQuery]
    ) -> list[ServiceRequestOutput] | Paginated[ServiceRequestOutput]:
        qs = self.get_queryset()
        if parsed_query.status is not None:
            qs = qs.filter(status=parsed_query.status)
        if parsed_query.property_id is not None:
            qs = qs.filter(property_id=parsed_query.property_id)
        items = [self.to_output(obj) for obj in qs]
        if parsed_query.page is not None:
            paginated = build_paginated_response(items, parsed_query.page, parsed_query.per_page)
            return self.ok(paginated)
        return self.ok(items)


class ServiceRequestDetailUpdateView(RetrieveAPIView, GenericController):
    model = ServiceRequest
    output_schema = ServiceRequestOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return ServiceRequest.objects.select_related("property", "tenant", "assigned_to").all()

    def get(self, parsed_path: Path[DetailPath]) -> ServiceRequestOutput:
        return super().get(parsed_path)

    def patch(
        self, parsed_path: Path[DetailPath], parsed_body: Body[ServiceRequestUpdateInput]
    ) -> ServiceRequestOutput:
        instance = self.get_object(pk=parsed_path.pk)
        data = parsed_body.model_dump(exclude_unset=True)
        for attr, value in data.items():
            setattr(instance, attr, value)
        instance.save()
        return self.ok(self.to_output(instance))


class ServiceRequestAssignView(GenericController):
    model = ServiceRequest
    output_schema = ServiceRequestOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return ServiceRequest.objects.select_related("property", "tenant", "assigned_to").all()

    def post(
        self, parsed_path: Path[DetailPath], parsed_body: Body[ServiceRequestAssignInput]
    ) -> ServiceRequestOutput:
        instance = self.get_object(pk=parsed_path.pk)
        instance.assigned_to_id = parsed_body.assigned_to_id
        instance.status = ServiceRequestStatus.IN_PROGRESS
        instance.save(update_fields=["assigned_to_id", "status", "updated_at"])
        return self.ok(self.to_output(instance), status_code=HTTPStatus.OK)


class ServiceRequestResolveView(GenericController):
    model = ServiceRequest
    output_schema = ServiceRequestOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return ServiceRequest.objects.select_related("property", "tenant", "assigned_to").all()

    def post(
        self, parsed_path: Path[DetailPath], parsed_body: Body[ServiceRequestResolveInput]
    ) -> ServiceRequestOutput:
        instance = self.get_object(pk=parsed_path.pk)
        instance.status = ServiceRequestStatus.RESOLVED
        instance.cost = parsed_body.cost
        instance.resolution_notes = parsed_body.resolution_notes
        instance.save(update_fields=["status", "cost", "resolution_notes", "updated_at"])
        return self.ok(self.to_output(instance), status_code=HTTPStatus.OK)
