import pydantic
from dmr import Body, Path, Query
from dmr.pagination import Paginated
from vas.models import ServiceCatalogItem

from api.v1.vas.schemas import (
    ServiceCatalogItemCreateInput,
    ServiceCatalogItemOutput,
    ServiceCatalogItemUpdateInput,
)
from core.api.permissions import require_role
from core.api.views import CreateAPIView, DetailPath, GenericController, ListAPIView
from core.constants import UserRole


class CatalogFilterQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20
    service_type: str | None = None
    is_active: bool | None = None


class ServiceCatalogListCreateView(CreateAPIView, ListAPIView):
    model = ServiceCatalogItem
    output_schema = ServiceCatalogItemOutput
    create_schema = ServiceCatalogItemCreateInput

    def get_queryset(self):
        return ServiceCatalogItem.objects.all()

    def get(
        self, parsed_query: Query[CatalogFilterQuery]
    ) -> list[ServiceCatalogItemOutput] | Paginated[ServiceCatalogItemOutput]:
        qs = self.get_queryset()
        if parsed_query.service_type is not None:
            qs = qs.filter(service_type=parsed_query.service_type)
        if parsed_query.is_active is not None:
            qs = qs.filter(is_active=parsed_query.is_active)
        items = [self.to_output(obj) for obj in qs]
        if parsed_query.page is not None:
            from core.utils.pagination import build_paginated_response

            return self.ok(build_paginated_response(items, parsed_query.page, parsed_query.per_page))
        return self.ok(items)

    @require_role(UserRole.MANAGEMENT)
    def post(self, parsed_body: Body[ServiceCatalogItemCreateInput]) -> ServiceCatalogItemOutput:
        return super().post(parsed_body)


class ServiceCatalogDetailView(GenericController):
    model = ServiceCatalogItem
    output_schema = ServiceCatalogItemOutput

    def get_queryset(self):
        return ServiceCatalogItem.objects.all()

    @require_role(UserRole.MANAGEMENT)
    def patch(
        self, parsed_path: Path[DetailPath], parsed_body: Body[ServiceCatalogItemUpdateInput]
    ) -> ServiceCatalogItemOutput:
        item = self.get_object(pk=parsed_path.pk)
        for attr, value in parsed_body.model_dump(exclude_unset=True).items():
            setattr(item, attr, value)
        item.save()
        return self.ok(self.to_output(item))
