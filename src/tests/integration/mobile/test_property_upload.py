import json
from datetime import UTC, datetime, timedelta

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from marketplace.models import Listing
from property.models import Amenity, Property

from core.constants import ListingStatus, PropertyStatus, UserRole
from tests.factories import DistrictFactory, UserFactory

pytestmark = pytest.mark.django_db

CONFIG_URL = "/api/v1/mobile/property-upload/config/"
SUBMIT_URL = "/api/v1/mobile/property-upload/submit/"

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_jwt(user, **overrides):
    import jwt

    payload = {
        "sub": str(user.id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "jti": overrides.pop("jti", "upload-token"),
    }
    payload.update(overrides)
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class TestMobilePropertyUploadConfig:
    def test_anonymous_config_shape(self, api_client):
        district = DistrictFactory(name="Chilanzar", city="Tashkent")
        amenity, _ = Amenity.objects.get_or_create(
            slug="wifi", defaults={"name": "Wi-Fi", "icon": "wifi", "is_active": True}
        )

        res = api_client.get(CONFIG_URL)
        assert res.status_code == 200
        data = res.json()["data"]

        assert "property_types" in data
        assert "districts" in data
        assert "furnishings" in data
        assert "amenities" in data
        assert "minimum_stays" in data
        assert "price_includes" in data
        assert "currencies" in data
        assert "public_offer" in data
        assert data["user_profile"] is None

        district_ids = [d["id"] for d in data["districts"]]
        assert district.id in district_ids

        amenity_slugs = [a["slug"] for a in data["amenities"]]
        assert amenity.slug in amenity_slugs

    def test_authenticated_config_populates_user_profile(self, api_client):
        user = UserFactory(first_name="Ali", last_name="Valiyev", email="ali@example.com", phone="+998901234567")
        res = api_client.get(CONFIG_URL, **_make_jwt(user))
        assert res.status_code == 200
        profile = res.json()["data"]["user_profile"]
        assert profile is not None
        assert profile["first_name"] == "Ali"
        assert profile["last_name"] == "Valiyev"
        assert profile["email"] == "ali@example.com"
        assert profile["phone"] == "+998901234567"


class TestMobilePropertyUploadSubmit:
    def test_unauthenticated_submit_rejected(self, api_client):
        res = api_client.post(SUBMIT_URL, data={"payload": "{}"})
        assert res.status_code == 401

    def test_missing_payload_rejected(self, api_client):
        user = UserFactory()
        res = api_client.post(SUBMIT_URL, data={}, **_make_jwt(user))
        assert res.status_code == 400

    def test_missing_or_fewer_than_five_photos_rejected(self, api_client):
        user = UserFactory()
        district = DistrictFactory()
        payload = {
            "name": "Cozy Apartment",
            "property_type": "apartment",
            "district_id": district.id,
            "rooms": 2,
            "floor": 3,
            "total_floors": 9,
            "area_sqm": 65,
            "furnishing": "furnished",
            "monthly_price": 500,
            "deposit_amount": 500,
            "currency": "USD",
            "minimum_stay": 6,
            "accept_offer": True,
        }
        # Only 4 photos
        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(4)]
        res = api_client.post(
            SUBMIT_URL,
            data={"payload": json.dumps(payload), "images": files},
            **_make_jwt(user),
        )
        assert res.status_code == 400
        assert "At least 5 photos are required" in res.json()["error"]

    def test_accept_offer_required(self, api_client):
        user = UserFactory()
        district = DistrictFactory()
        payload = {
            "name": "Cozy Apartment",
            "property_type": "apartment",
            "district_id": district.id,
            "rooms": 2,
            "floor": 3,
            "total_floors": 9,
            "area_sqm": 65,
            "furnishing": "furnished",
            "monthly_price": 500,
            "deposit_amount": 500,
            "currency": "USD",
            "minimum_stay": 6,
            "accept_offer": False,
        }
        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(5)]
        res = api_client.post(
            SUBMIT_URL,
            data={"payload": json.dumps(payload), "images": files},
            **_make_jwt(user),
        )
        assert res.status_code == 400
        assert "accept the public offer" in res.json()["error"].lower()

    def test_invalid_floor_bounds_rejected(self, api_client):
        user = UserFactory()
        district = DistrictFactory()
        payload = {
            "name": "Cozy Apartment",
            "property_type": "apartment",
            "district_id": district.id,
            "rooms": 2,
            "floor": 10,
            "total_floors": 9,  # floor > total_floors
            "area_sqm": 65,
            "furnishing": "furnished",
            "monthly_price": 500,
            "deposit_amount": 500,
            "currency": "USD",
            "minimum_stay": 6,
            "accept_offer": True,
        }
        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(5)]
        res = api_client.post(
            SUBMIT_URL,
            data={"payload": json.dumps(payload), "images": files},
            **_make_jwt(user),
        )
        assert res.status_code == 400

    def test_successful_submit(self, api_client):
        user = UserFactory(first_name="Jasur", role=UserRole.TENANT)
        district = DistrictFactory(name="Yunusabad")
        Amenity.objects.get_or_create(slug="wifi", defaults={"name": "Wi-Fi", "icon": "wifi", "is_active": True})
        Amenity.objects.get_or_create(slug="ac", defaults={"name": "Air Conditioning", "icon": "ac", "is_active": True})

        payload = {
            "name": "Modern 2-room apartment in Yunusabad",
            "property_type": "apartment",
            "district_id": district.id,
            "rooms": 2,
            "floor": 4,
            "total_floors": 9,
            "area_sqm": 72,
            "furnishing": "furnished",
            "description": "Bright and renovated apartment near metro.",
            "amenities": ["wifi", "ac"],
            "monthly_price": 650,
            "deposit_amount": 650,
            "currency": "USD",
            "minimum_stay": 6,
            "price_includes": ["internet", "water"],
            "accept_offer": True,
            "contact": {
                "first_name": "Jasur",
                "last_name": "Karimov",
                "email": "jasur@example.com",
                "phone": "+998901112233",
            },
        }

        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(5)]
        res = api_client.post(
            SUBMIT_URL,
            data={"payload": json.dumps(payload), "images": files},
            **_make_jwt(user),
        )

        assert res.status_code == 201
        data = res.json()["data"]
        assert "id" in data
        assert "property_id" in data
        assert data["status"] == ListingStatus.PENDING_REVIEW

        # Verify DB records
        prop = Property.objects.get(pk=data["property_id"])
        assert prop.name == payload["name"]
        assert prop.owner == user
        assert prop.status == PropertyStatus.PENDING_REVIEW
        assert prop.rooms == 2
        assert prop.floor == 4
        assert prop.total_floors == 9
        assert prop.area_sqm == 72
        assert prop.amenities.count() == 2
        assert prop.photos.count() == 5

        # Primary photo check
        photos = list(prop.photos.order_by("sort_order"))
        assert photos[0].is_primary is True
        assert photos[1].is_primary is False

        # Listing check
        listing = Listing.objects.get(pk=data["id"])
        assert listing.property == prop
        assert listing.status == ListingStatus.PENDING_REVIEW
        assert listing.is_active is False
        assert listing.monthly_price == 650
        assert listing.deposit_amount == 650
        assert listing.currency == "USD"
        assert listing.minimum_stay == 6
        assert listing.price_includes == ["internet", "water"]

        # User promoted to OWNER
        user.refresh_from_db()
        assert user.role == UserRole.OWNER
        assert user.last_name == "Karimov"
        assert user.email == "jasur@example.com"

    def test_submit_without_name_autogenerates_title(self, api_client):
        user = UserFactory(first_name="NoNameUser")
        district = DistrictFactory(name="Mirzo Ulugbek")

        payload = {
            "property_type": "apartment",
            "district_id": district.id,
            "rooms": 3,
            "floor": 2,
            "total_floors": 5,
            "area_sqm": 85,
            "furnishing": "semi_furnished",
            "monthly_price": 800,
            "currency": "USD",
            "accept_offer": True,
        }

        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(5)]
        res = api_client.post(
            SUBMIT_URL,
            data={"payload": json.dumps(payload), "images": files},
            **_make_jwt(user),
        )

        assert res.status_code == 201
        data = res.json()["data"]
        prop = Property.objects.get(pk=data["property_id"])
        assert prop.name == "3-room Apartment in Mirzo Ulugbek"
        assert prop.rooms == 3
        assert prop.area_sqm == 85
        assert prop.deposit_amount == 0
