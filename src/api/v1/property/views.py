from dmr import Body, Path, Query
from dmr.pagination import Paginated
from property.models import Property

from api.v1.property.schemas import PropertyCreateInput, PropertyOutput, PropertyUpdateInput
from core.api.permissions import require_role
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
from core.constants import UserRole


class PropertyListCreateView(CreateAPIView, ListAPIView):
    model = Property
    output_schema = PropertyOutput
    create_schema = PropertyCreateInput
    update_schema = PropertyUpdateInput

    def get_queryset(self):
        user = self.request.user
        qs = Property.objects.select_related("district", "owner")
        if user.role == UserRole.OWNER:
            return qs.filter(owner=user)
        return qs.all()

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
        user = self.request.user
        qs = Property.objects.select_related("district", "owner")
        if user.role == UserRole.OWNER:
            return qs.filter(owner=user)
        return qs.all()

    @require_role(UserRole.MANAGEMENT, UserRole.OWNER)
    def get(self, parsed_path: Path[DetailPath]) -> PropertyOutput:
        return super().get(parsed_path)

    @require_role(UserRole.MANAGEMENT)
    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[PropertyUpdateInput]) -> PropertyOutput:
        return super().patch(parsed_path, parsed_body)

    @require_role(UserRole.MANAGEMENT)
    def delete(self, parsed_path: Path[DetailPath]) -> DeleteData:
        return super().delete(parsed_path)
