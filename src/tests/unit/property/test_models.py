import pytest
from django.db.utils import IntegrityError
from property.models import District, Property

from tests.factories import DistrictFactory, PropertyFactory


@pytest.mark.django_db
class TestDistrictModel:
    def test_create_district(self):
        district = DistrictFactory(name="Yunusobod", city="Toshkent")
        assert district.name == "Yunusobod"
        assert district.city == "Toshkent"
        assert str(district) == "Yunusobod, Toshkent"

    def test_district_soft_delete(self):
        district = DistrictFactory()
        district.delete()
        assert district.deleted_at is not None
        assert not District.objects.filter(id=district.id).exists()

    def test_district_unique_name(self):
        DistrictFactory(name="Unique District")
        with pytest.raises(IntegrityError):
            DistrictFactory(name="Unique District")


@pytest.mark.django_db
class TestPropertyModel:
    @pytest.fixture(autouse=True)
    def setup(self, district, owner):
        self.district = district
        self.owner = owner

    def test_create_property(self):
        prop = PropertyFactory(district=self.district, owner=self.owner, name="Sunny Apartment")
        assert prop.name == "Sunny Apartment"
        assert prop.status == "vacant"
        assert prop.tariff == "standard"
        assert prop.score == 0.0
        assert prop.owner == self.owner
        assert prop.district == self.district

    def test_property_str(self, property_obj):
        assert str(property_obj) == f"{property_obj.name} (Vacant)"

    def test_property_soft_delete(self, property_obj):
        property_obj.delete()
        assert property_obj.deleted_at is not None
        assert not Property.objects.filter(id=property_obj.id).exists()

    def test_property_status_choices(self, property_obj):
        property_obj.status = "rented"
        property_obj.save()
        assert property_obj.get_status_display() == "Rented"

    def test_district_protect_on_delete(self, owner):
        district = DistrictFactory(name="Protected District")
        PropertyFactory(district=district, owner=owner)
        with pytest.raises(IntegrityError):
            district.delete()
