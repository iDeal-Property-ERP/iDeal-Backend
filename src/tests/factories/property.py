import factory
from property.models import District, Property, PropertyPhoto

from .account import OwnerFactory


class DistrictFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = District

    name = factory.Sequence(lambda n: f"District {n}")
    city = "Toshkent"


class PropertyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Property

    name = factory.Sequence(lambda n: f"Property {n}")
    address = factory.Faker("street_address")
    district = factory.SubFactory(DistrictFactory)
    rooms = factory.Faker("random_int", min=1, max=5)
    area_sqm = factory.Faker("random_int", min=20, max=200)
    floor = factory.Faker("random_int", min=1, max=15)
    total_floors = factory.Faker("random_int", min=1, max=20)
    owner = factory.SubFactory(OwnerFactory)
    ask_price = 500.00
    ask_currency = "USD"
    owner_guaranteed_price = 450.00
    owner_guaranteed_currency = "USD"
    tenant_charge_price = 550.00
    tenant_charge_currency = "USD"


class PropertyPhotoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PropertyPhoto

    property = factory.SubFactory(PropertyFactory)
    is_primary = False
    sort_order = 0
