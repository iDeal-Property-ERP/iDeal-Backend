# type: ignore
import pytest
from property.models import Property
from property.services.validation import validate_and_normalize_landmark
from pydantic import ValidationError

from api.v1.marketplace.schemas import PublicListingSubmitInput
from api.v1.mobile.property_upload.schemas import MobilePropertyUploadInput
from api.v1.owner.schemas import OwnerListingSubmitPayload, OwnerOnboardingCreateInput
from api.v1.property.schemas import PropertyCreateInput, PropertySubmissionInput, PropertyUpdateInput
from tests.factories import DistrictFactory, OwnerFactory


class TestLandmarkValidation:
    def test_empty_or_none_returns_none(self):
        assert validate_and_normalize_landmark(None) is None
        assert validate_and_normalize_landmark("") is None
        assert validate_and_normalize_landmark("   ") is None
        assert validate_and_normalize_landmark("\t \n ") is None

    def test_whitespace_trimmed_and_collapsed(self):
        assert validate_and_normalize_landmark("  Near   Grand   Mir   Hotel  ") == "Near Grand Mir Hotel"
        assert validate_and_normalize_landmark("Next to Metro") == "Next to Metro"

    def test_five_words_accepted(self):
        assert validate_and_normalize_landmark("One two three four five") == "One two three four five"

    def test_six_words_rejected(self):
        with pytest.raises(ValueError, match="Landmark cannot exceed 5 words"):
            validate_and_normalize_landmark("One two three four five six")

    def test_hundred_chars_accepted(self):
        # 5 words totalling exactly 100 characters
        # 4 words of 19 chars + 1 word of 20 chars + 4 spaces = 76 + 20 + 4 = 100
        w1 = "a" * 19
        w2 = "b" * 19
        w3 = "c" * 19
        w4 = "d" * 19
        w5 = "e" * 20
        raw = f"{w1} {w2} {w3} {w4} {w5}"
        assert len(raw) == 100
        assert validate_and_normalize_landmark(raw) == raw

    def test_over_hundred_chars_rejected(self):
        w1 = "a" * 20
        w2 = "b" * 20
        w3 = "c" * 20
        w4 = "d" * 20
        w5 = "e" * 20
        raw = f"{w1} {w2} {w3} {w4} {w5}"  # 104 chars, 5 words
        assert len(raw) == 104
        with pytest.raises(ValueError, match="Landmark cannot exceed 100 characters"):
            validate_and_normalize_landmark(raw)


@pytest.mark.django_db
class TestLandmarkSchemas:
    def test_property_create_schema_normalizes_landmark(self):
        district = DistrictFactory()
        owner = OwnerFactory()
        data = PropertyCreateInput.model_validate(
            {
                "name": "Test Property",
                "address": "Amir Temur 1",
                "landmark": "  Near   Hotel   Uzbekistan  ",
                "district_id": district.id,
                "rooms": 2,
                "area_sqm": 60,
                "floor": 3,
                "total_floors": 9,
                "owner_id": owner.id,
                "ask_price": 500,
                "owner_guaranteed_price": 450,
                "tenant_charge_price": 550,
            }
        )
        assert data.landmark == "Near Hotel Uzbekistan"

    def test_property_create_schema_rejects_excess_words(self):
        district = DistrictFactory()
        owner = OwnerFactory()
        with pytest.raises(ValidationError, match="Landmark cannot exceed 5 words"):
            PropertyCreateInput.model_validate(
                {
                    "name": "Test Property",
                    "address": "Amir Temur 1",
                    "landmark": "one two three four five six",
                    "district_id": district.id,
                    "rooms": 2,
                    "area_sqm": 60,
                    "floor": 3,
                    "total_floors": 9,
                    "owner_id": owner.id,
                    "ask_price": 500,
                    "owner_guaranteed_price": 450,
                    "tenant_charge_price": 550,
                }
            )

    @pytest.mark.parametrize(
        "schema,payload",
        [
            (PropertyUpdateInput, {"landmark": "  Near   Metro  "}),
            (
                PropertySubmissionInput,
                {
                    "district_id": 1,
                    "rooms": 1,
                    "area_sqm": 40,
                    "floor": 1,
                    "total_floors": 5,
                    "ask_price": 300,
                    "landmark": "  Near   Park  ",
                },
            ),
            (
                OwnerOnboardingCreateInput,
                {
                    "name": "P",
                    "address": "A",
                    "district_id": 1,
                    "rooms": 1,
                    "area_sqm": 40,
                    "floor": 1,
                    "ask_price": 300,
                    "accept_offer": True,
                    "landmark": "  Near   Square  ",
                },
            ),
            (
                OwnerListingSubmitPayload,
                {
                    "district_id": 1,
                    "rooms": 1,
                    "area_sqm": 40,
                    "floor": 1,
                    "monthly_price": 300,
                    "accept_offer": True,
                    "landmark": "  Near   Bazaar  ",
                },
            ),
            (
                PublicListingSubmitInput,
                {
                    "contact": {"first_name": "T", "email": "t@e.co", "phone": "+998901234567"},
                    "property_type": "apartment",
                    "name": "P",
                    "district_id": 1,
                    "rooms": 1,
                    "area_sqm": 40,
                    "furnishing": "furnished",
                    "monthly_price": 300,
                    "deposit_amount": 0,
                    "landmark": "  Near   School  ",
                },
            ),
            (
                MobilePropertyUploadInput,
                {
                    "property_type": "apartment",
                    "district_id": 1,
                    "rooms": 1,
                    "area_sqm": 40,
                    "floor": 1,
                    "furnishing": "furnished",
                    "monthly_price": 300,
                    "accept_offer": True,
                    "landmark": "  Near   Hospital  ",
                },
            ),
        ],
    )
    def test_schemas_normalize_valid_landmark(self, schema, payload):
        validated = schema.model_validate(payload)
        assert validated.landmark is not None
        assert "  " not in validated.landmark
        assert not validated.landmark.startswith(" ")
        assert not validated.landmark.endswith(" ")


@pytest.mark.django_db
class TestPropertyModelLandmark:
    def test_property_multilingual_landmark(self):
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = Property.objects.create(
            name="Test",
            name_en="Test EN",
            name_uz="Test UZ",
            name_ru="Test RU",
            address="Addr",
            district=district,
            owner=owner,
            rooms=2,
            area_sqm=50,
            floor=2,
            total_floors=5,
            landmark="Near Metro",
            landmark_en="Near Metro",
            landmark_uz="Metro yaqinida",
            landmark_ru="Рядом с метро",
        )
        prop.refresh_from_db()
        assert prop.landmark_en == "Near Metro"
        assert prop.landmark_uz == "Metro yaqinida"
        assert prop.landmark_ru == "Рядом с метро"

    def test_property_clean_normalizes_landmark(self):
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = Property(
            name="Test",
            address="Addr",
            district=district,
            owner=owner,
            rooms=2,
            area_sqm=50,
            floor=2,
            total_floors=5,
            landmark="  Near   Chorsu   Bazaar  ",
        )
        prop.clean()
        assert prop.landmark == "Near Chorsu Bazaar"

    def test_property_clean_rejects_excess_words(self):
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = Property(
            name="Test",
            address="Addr",
            district=district,
            owner=owner,
            rooms=2,
            area_sqm=50,
            floor=2,
            total_floors=5,
            landmark="one two three four five six",
        )
        with pytest.raises(Exception, match="Landmark cannot exceed 5 words"):
            prop.clean()
