import pytest
from django.core.exceptions import ValidationError
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

    def test_clean_rejects_floor_above_total_floors(self):
        prop = PropertyFactory.build(floor=7, total_floors=5)

        with pytest.raises(ValidationError, match="Floor cannot be greater than total floors"):
            prop.clean()

    @pytest.mark.parametrize(("floor", "total_floors"), [(5, 5), (None, 5), (5, None)])
    def test_clean_accepts_valid_or_partial_floor_bounds(self, floor, total_floors):
        prop = PropertyFactory(floor=floor, total_floors=total_floors)

        prop.clean()

    def test_database_constraint_rejects_raw_invalid_floor_update(self):
        prop = PropertyFactory(floor=1, total_floors=5)

        with pytest.raises(IntegrityError):
            Property.objects.filter(pk=prop.pk).update(floor=99)

    def test_property_created_by_and_contact_phone_persistence(self, management):
        prop = PropertyFactory(created_by=management, contact_phone="+998901234567")
        assert prop.created_by == management
        assert prop.contact_phone == "+998901234567"

    def test_property_creator_protect_on_delete(self, management):
        PropertyFactory(created_by=management)
        with pytest.raises(IntegrityError):
            management.delete()

    def test_property_creator_is_immutable(self, management, owner):
        prop = PropertyFactory(created_by=management)
        prop.created_by = owner
        with pytest.raises(ValidationError, match="Property creator cannot be changed"):
            prop.save()
