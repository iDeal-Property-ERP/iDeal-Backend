from dmr import Body, Path, Query
from dmr.pagination import Paginated
from property.models import Property

from api.v1.property.schemas import PropertyCreateInput, PropertyOutput, PropertyUpdateInput
from core.api.schemas import DeleteData
from core.api.views import (
    CreateAPIView,
    DeleteAPIView,
    DetailPath,
    ListAPIView,
    ListQuery,
    PartialUpdateAPIView,
    RetrieveAPIView,
)


class PropertyListCreateView(CreateAPIView, ListAPIView):
    model = Property
    output_schema = PropertyOutput
    create_schema = PropertyCreateInput
    update_schema = PropertyUpdateInput

    def get_queryset(self):
        return Property.objects.select_related("district", "owner").all()

    def post(self, parsed_body: Body[PropertyCreateInput]) -> PropertyOutput:
        return super().post(parsed_body)

    def get(self, parsed_query: Query[ListQuery]) -> list[PropertyOutput] | Paginated[PropertyOutput]:
        return super().get(parsed_query)


class PropertyDetailView(RetrieveAPIView, PartialUpdateAPIView, DeleteAPIView):
    model = Property
    output_schema = PropertyOutput
    create_schema = PropertyCreateInput
    update_schema = PropertyUpdateInput

    def get_queryset(self):
        return Property.objects.select_related("district", "owner").all()

    def get(self, parsed_path: Path[DetailPath]) -> PropertyOutput:
        return super().get(parsed_path)

    def patch(
        self, parsed_path: Path[DetailPath], parsed_body: Body[PropertyUpdateInput]
    ) -> PropertyOutput:
        return super().patch(parsed_path, parsed_body)

    def delete(self, parsed_path: Path[DetailPath]) -> DeleteData:
        return super().delete(parsed_path)
