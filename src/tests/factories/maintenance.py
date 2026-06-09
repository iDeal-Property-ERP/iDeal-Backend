import factory
from maintenance.models import ServiceRequest, ServiceRequestPhoto

from core.constants import ServiceRequestPriority, ServiceRequestStatus

from .account import TenantFactory
from .property import PropertyFactory


class ServiceRequestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ServiceRequest

    property = factory.SubFactory(PropertyFactory)
    tenant = factory.SubFactory(TenantFactory)
    assigned_to = None
    title = factory.Faker("sentence", nb_words=4)
    description = factory.Faker("text", max_nb_chars=300)
    priority = ServiceRequestPriority.MEDIUM
    status = ServiceRequestStatus.OPEN
    cost = None
    resolution_notes = None


class ServiceRequestPhotoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ServiceRequestPhoto

    service_request = factory.SubFactory(ServiceRequestFactory)
    image = factory.django.ImageField(color="blue")
