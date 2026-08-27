import json

import pytest

from core.constants import UserRole
from tests.factories import AmenityFactory, DistrictFactory, FaqItemFactory, PublicOfferFactory, UserFactory


def _make_jwt(user):
    from datetime import UTC, datetime, timedelta

    import jwt
    from django.conf import settings

    payload = {
        "sub": str(user.id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "jti": "loc-token",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.mark.django_db
class TestManagementLocalizationAPI:
    def test_district_crud_with_translations(self, api_client):
        mgmt = UserFactory(role=UserRole.MANAGEMENT)
        auth = _make_jwt(mgmt)

        # Create
        payload = {
            "name": "Yunusobod",
            "city": "Toshkent",
            "translations": {
                "en": {"name": "Yunusabad", "city": "Tashkent"},
                "uz": {"name": "Yunusobod", "city": "Toshkent"},
                "ru": {"name": "Юнусабад", "city": "Ташкент"},
            },
        }
        res = api_client.post(
            "/api/v1/management/districts/",
            data=json.dumps(payload),
            content_type="application/json",
            **auth,
        )
        assert res.status_code == 201
        data = res.json()["data"]
        district_id = data["id"]
        assert data["translations"]["ru"]["name"] == "Юнусабад"

        # Update
        patch_payload = {
            "translations": {
                "en": {"name": "Yunusabad District", "city": "Tashkent City"},
                "uz": {"name": "Yunusobod Tumani", "city": "Toshkent Shahri"},
                "ru": {"name": "Юнусабадский район", "city": "город Ташкент"},
            }
        }
        res_patch = api_client.patch(
            f"/api/v1/management/districts/{district_id}/",
            data=json.dumps(patch_payload),
            content_type="application/json",
            **auth,
        )
        assert res_patch.status_code == 200
        patch_data = res_patch.json()["data"]
        assert patch_data["translations"]["uz"]["name"] == "Yunusobod Tumani"

    def test_amenity_crud_with_translations(self, api_client):
        mgmt = UserFactory(role=UserRole.MANAGEMENT)
        auth = _make_jwt(mgmt)

        payload = {
            "name": "Wi-Fi",
            "slug": "wifi-high-speed",
            "icon": "wifi",
            "translations": {
                "en": {"name": "High-Speed Wi-Fi"},
                "uz": {"name": "Tezkor Wi-Fi"},
                "ru": {"name": "Скоростной Wi-Fi"},
            },
        }
        res = api_client.post(
            "/api/v1/management/amenities/",
            data=json.dumps(payload),
            content_type="application/json",
            **auth,
        )
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["translations"]["ru"]["name"] == "Скоростной Wi-Fi"

    def test_faq_crud_with_translations(self, api_client):
        mgmt = UserFactory(role=UserRole.MANAGEMENT)
        auth = _make_jwt(mgmt)

        payload = {
            "question": "How to rent?",
            "answer": "Contact us.",
            "translations": {
                "en": {"question": "How to rent?", "answer": "Contact us."},
                "uz": {"question": "Qanday ijaraga olinadi?", "answer": "Biz bilan bog'laning."},
                "ru": {"question": "Как арендовать?", "answer": "Свяжитесь с нами."},
            },
        }
        res = api_client.post(
            "/api/v1/management/faqs/",
            data=json.dumps(payload),
            content_type="application/json",
            **auth,
        )
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["translations"]["uz"]["question"] == "Qanday ijaraga olinadi?"

    def test_public_offer_crud_with_translations(self, api_client):
        mgmt = UserFactory(role=UserRole.MANAGEMENT)
        auth = _make_jwt(mgmt)

        payload = {
            "version": "v1.2",
            "body": "Terms",
            "translations": {
                "en": {"body": "Terms in English"},
                "uz": {"body": "Shartlar o'zbek tilida"},
                "ru": {"body": "Условия на русском"},
            },
        }
        res = api_client.post(
            "/api/v1/management/public-offers/",
            data=json.dumps(payload),
            content_type="application/json",
            **auth,
        )
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["translations"]["ru"]["body"] == "Условия на русском"

    def test_localization_status_endpoint(self, api_client):
        mgmt = UserFactory(role=UserRole.MANAGEMENT)
        auth = _make_jwt(mgmt)

        DistrictFactory()
        AmenityFactory()
        FaqItemFactory()
        PublicOfferFactory()

        res = api_client.get("/api/v1/management/localization/status/", **auth)
        assert res.status_code == 200
        data = res.json()["data"]
        assert "properties" in data
        assert "districts" in data
        assert "amenities" in data
        assert "faqs" in data
        assert "public_offers" in data
