import factory
from vas.models import ServiceCatalogItem, ServiceOrder

from core.constants import Currency, VASOrderStatus, VASServiceType

from .account import TenantFactory
from .property import PropertyFactory


class ServiceCatalogItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ServiceCatalogItem

    service_type = VASServiceType.CLEANING
    name = factory.Sequence(lambda n: f"Service {n}")
    name_en = factory.LazyAttribute(lambda o: o.name)
    name_uz = factory.LazyAttribute(lambda o: o.name)
    name_ru = factory.LazyAttribute(lambda o: o.name)
    description = factory.Faker("sentence")
    description_en = factory.LazyAttribute(lambda o: o.description)
    description_uz = factory.LazyAttribute(lambda o: o.description)
    description_ru = factory.LazyAttribute(lambda o: o.description)
    partner_name = factory.Faker("company")
    base_price = 100.00
    currency = Currency.USD
    commission_rate = 15.00
    cashback_rate = 5.00
    is_active = True


class ServiceOrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ServiceOrder

    catalog_item = factory.SubFactory(ServiceCatalogItemFactory)
    tenant = factory.SubFactory(TenantFactory)
    property = factory.SubFactory(PropertyFactory)
    lease = None
    status = VASOrderStatus.REQUESTED
    cost = 100.00
    currency = Currency.USD
