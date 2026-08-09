import pytest
from pydantic import ValidationError

from api.v1.management.schemas import OneOffDealCreateInput
from api.v1.marketplace.schemas import PublicListingSubmitInput
from api.v1.owner.schemas import OwnerListingCreateInput, OwnerListingUpdateInput, OwnerOnboardingCreateInput
from api.v1.property.schemas import PropertyCreateInput, PropertyUpdateInput
from tests.factories import DistrictFactory, OwnerFactory


@pytest.mark.django_db
class TestFloorBoundSchemas:
    def test_property_create_rejects_floor_above_total_floors(self):
        district = DistrictFactory()
        owner = OwnerFactory()

        with pytest.raises(ValidationError, match="Floor cannot be greater than total floors"):
            PropertyCreateInput.model_validate(
                {
                    "name": "Invalid floors",
                    "address": "Tashkent",
                    "district_id": district.id,
                    "rooms": 2,
                    "area_sqm": 60,
                    "floor": 7,
                    "total_floors": 5,
                    "owner_id": owner.id,
                    "ask_price": 500,
                    "owner_guaranteed_price": 450,
                    "tenant_charge_price": 550,
                }
            )

    @pytest.mark.parametrize(
        ("schema", "payload"),
        [
            (PropertyUpdateInput, {"floor": 7, "total_floors": 5}),
            (
                PublicListingSubmitInput,
                {
                    "contact": {"first_name": "Test", "email": "test@example.com", "phone": "+998901234567"},
                    "property_type": "apartment",
                    "name": "Invalid floors",
                    "district_id": 1,
                    "rooms": 2,
                    "area_sqm": 60,
                    "floor": 7,
                    "total_floors": 5,
                    "furnishing": "furnished",
                    "monthly_price": 500,
                    "deposit_amount": 500,
                },
            ),
            (
                OneOffDealCreateInput,
                {
                    "name": "Invalid floors",
                    "floor": 7,
                    "total_floors": 5,
                    "seller": {"name": "Seller", "phone": "+998901234567"},
                    "channel": "marketplace",
                },
            ),
            (
                OwnerOnboardingCreateInput,
                {
                    "name": "Invalid floors",
                    "address": "Tashkent",
                    "district_id": 1,
                    "rooms": 2,
                    "area_sqm": 60,
                    "floor": 7,
                    "total_floors": 5,
                    "ask_price": 500,
                    "accept_offer": True,
                },
            ),
            (
                OwnerListingCreateInput,
                {
                    "name": "Invalid floors",
                    "district_id": 1,
                    "rooms": 2,
                    "area_sqm": 60,
                    "floor": 7,
                    "total_floors": 5,
                },
            ),
            (OwnerListingUpdateInput, {"floor": 7, "total_floors": 5}),
        ],
    )
    def test_schema_rejects_floor_above_total_floors(self, schema, payload):
        with pytest.raises(ValidationError, match="Floor cannot be greater than total floors"):
            schema.model_validate(payload)
