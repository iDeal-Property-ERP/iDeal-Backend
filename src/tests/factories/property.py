import factory
from property.models import Amenity, District, Property, PropertyPhoto, VerificationVisit

from .account import OwnerFactory


class DistrictFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = District

    name = factory.Sequence(lambda n: f"District {n}")
    name_en = factory.LazyAttribute(lambda o: o.name)
    name_uz = factory.LazyAttribute(lambda o: o.name)
    name_ru = factory.LazyAttribute(lambda o: o.name)
    city = "Toshkent"
    city_en = factory.LazyAttribute(lambda o: o.city)
    city_uz = factory.LazyAttribute(lambda o: o.city)
    city_ru = factory.LazyAttribute(lambda o: o.city)


class AmenityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Amenity

    name = factory.Sequence(lambda n: f"Amenity {n}")
    name_en = factory.LazyAttribute(lambda o: o.name)
    name_uz = factory.LazyAttribute(lambda o: o.name)
    name_ru = factory.LazyAttribute(lambda o: o.name)
    slug = factory.Sequence(lambda n: f"amenity-{n}")
    icon = "wifi"
    is_active = True


class PropertyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Property

    name = factory.Sequence(lambda n: f"Property {n}")
    name_en = factory.LazyAttribute(lambda o: o.name)
    name_uz = factory.LazyAttribute(lambda o: o.name)
    name_ru = factory.LazyAttribute(lambda o: o.name)
    description = "Test Property Description"
    description_en = "Test Property Description"
    description_uz = "Test Property Description"
    description_ru = "Test Property Description"
    address = factory.Faker("street_address")
    district = factory.SubFactory(DistrictFactory)
    rooms = factory.Faker("random_int", min=1, max=5)
    area_sqm = factory.Faker("random_int", min=20, max=200)
    total_floors = factory.Faker("random_int", min=1, max=20)
    floor = factory.LazyAttribute(lambda obj: obj.total_floors)
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


class VerificationVisitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VerificationVisit

    property = factory.SubFactory(PropertyFactory)
    scheduled_for = factory.Faker("future_datetime", tzinfo=None)
