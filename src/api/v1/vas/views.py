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
    search: str | None = None


class ServiceCatalogListCreateView(CreateAPIView, ListAPIView):
    model = ServiceCatalogItem
    output_schema = ServiceCatalogItemOutput
    create_schema = ServiceCatalogItemCreateInput

    def get_queryset(self):
        return ServiceCatalogItem.objects.all()

    def to_output(self, instance: ServiceCatalogItem) -> dict:
        from core.services.localization import LocalizedContentService

        data = ServiceCatalogItemOutput.model_validate(instance).model_dump(mode="json")
        data["translations"] = LocalizedContentService().extract_translations(instance, ["name", "description"])
        return data

    def get(
        self, parsed_query: Query[CatalogFilterQuery]
    ) -> list[ServiceCatalogItemOutput] | Paginated[ServiceCatalogItemOutput]:
        qs = self.get_queryset()
        if parsed_query.service_type is not None:
            qs = qs.filter(service_type=parsed_query.service_type)
        if parsed_query.is_active is not None:
            qs = qs.filter(is_active=parsed_query.is_active)
        if parsed_query.search:
            from django.db.models import Q

            qs = qs.filter(
                Q(name__icontains=parsed_query.search)
                | Q(name_en__icontains=parsed_query.search)
                | Q(name_uz__icontains=parsed_query.search)
                | Q(name_ru__icontains=parsed_query.search)
                | Q(partner_name__icontains=parsed_query.search)
                | Q(description__icontains=parsed_query.search)
            )
        items = [self.to_output(obj) for obj in qs]
        if parsed_query.page is not None:
            from core.utils.pagination import build_paginated_response

            return self.ok(build_paginated_response(items, parsed_query.page, parsed_query.per_page))
        return self.ok(items)

    def perform_create(self, validated_data: dict):
        from core.services.localization import LocalizedContentService

        translations = validated_data.pop("translations", None)
        item = super().perform_create(validated_data)
        if translations:
            LocalizedContentService().apply_translations(item, translations, ["name", "description"])
            item.save()
        return item

    @require_role(UserRole.MANAGEMENT)
    def post(self, parsed_body: Body[dict]) -> dict:
        return super().post(parsed_body)


class ServiceCatalogDetailView(GenericController):
    model = ServiceCatalogItem
    output_schema = ServiceCatalogItemOutput

    def get_queryset(self):
        return ServiceCatalogItem.objects.all()

    def to_output(self, instance: ServiceCatalogItem) -> dict:
        from core.services.localization import LocalizedContentService

        data = ServiceCatalogItemOutput.model_validate(instance).model_dump(mode="json")
        data["translations"] = LocalizedContentService().extract_translations(instance, ["name", "description"])
        return data

    @require_role(UserRole.MANAGEMENT)
    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[dict]) -> dict:
        from core.services.localization import LocalizedContentService

        item = self.get_object(pk=parsed_path.pk)
        data = self._validate_body(ServiceCatalogItemUpdateInput, parsed_body, exclude_unset=True)
        translations = data.pop("translations", None)
        for attr, value in data.items():
            setattr(item, attr, value)
        if translations:
            LocalizedContentService().apply_translations(item, translations, ["name", "description"])
        item.save()
        return self.ok(self.to_output(item))
