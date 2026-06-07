from property.models import Property

from api.v1.property.schemas import PropertyCreateInput, PropertyOutput, PropertyUpdateInput
from core.api.views import CreateAPIView, DeleteAPIView, ListAPIView, PartialUpdateAPIView, RetrieveAPIView


class PropertyListCreateView(CreateAPIView, ListAPIView):
    model = Property
    output_schema = PropertyOutput
    create_schema = PropertyCreateInput
    update_schema = PropertyUpdateInput

    def get_queryset(self):
        return Property.objects.select_related("district", "owner").all()


class PropertyDetailView(RetrieveAPIView, PartialUpdateAPIView, DeleteAPIView):
    model = Property
    output_schema = PropertyOutput
    create_schema = PropertyCreateInput
    update_schema = PropertyUpdateInput

    def get_queryset(self):
        return Property.objects.select_related("district", "owner").all()
