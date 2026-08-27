import json
from datetime import UTC, datetime, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from property.models import Property, VerificationVisit

from core.constants import ListingStatus, PropertyEngagementType, PropertyStatus
from tests.factories import DistrictFactory, ListingFactory, OwnerFactory, PropertyFactory, PropertyPhotoFactory
from tests.integration.property.test_api import _make_jwt

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _upload(api_client, management, pk, n):
    files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(n)]
    return api_client.post(
        f"/api/v1/properties/{pk}/photos/",
        data={"images": files},
        **_make_jwt(management),
    )


@pytest.mark.django_db
class TestPropertySubmissions:
    def test_submit_managed_property_atomic(self, api_client, management):
        district = DistrictFactory()
        owner = OwnerFactory()
        payload = {
            "engagement_type": "managed",
            "name": "Chilonzor Sunrise 9-3",
            "address": "Chilonzor 9",
            "district_id": district.id,
            "owner_id": owner.id,
            "property_type": "apartment",
            "rooms": 3,
            "area_sqm": 75,
            "floor": 3,
            "total_floors": 9,
            "furnishing": "furnished",
            "ask_price": "600.00",
            "deposit_amount": "600.00",
            "currency": "USD",
            "amenities": ["wifi"],
        }
        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(5)]
        response = api_client.post(
            "/api/v1/properties/submit/",
            data={"payload": json.dumps(payload), "images": files},
            **_make_jwt(management),
        )
        print("DEBUG RESPONSE:", response.status_code, response.content)
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["status"] == PropertyStatus.VACANT
        assert data["name"] == "Chilonzor Sunrise 9-3"
        assert len(data["photos"]) == 5
        assert data["photos"][0]["is_primary"] is True

        prop = Property.objects.get(pk=data["id"])
        assert prop.status == PropertyStatus.VACANT
        assert prop.listing.status == "published"
        assert prop.listing.is_active is True

    def test_submit_managed_property_with_verification(self, api_client, management):
        district = DistrictFactory()
        owner = OwnerFactory()
        when = (datetime.now(UTC) + timedelta(days=2)).isoformat()
        payload = {
            "engagement_type": "managed",
            "name": "Verification Property",
            "district_id": district.id,
            "owner_id": owner.id,
            "rooms": 2,
            "area_sqm": 50,
            "floor": 1,
            "total_floors": 5,
            "ask_price": "450.00",
            "schedule_verification_at": when,
        }
        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(5)]
        response = api_client.post(
            "/api/v1/properties/submit/",
            data={"payload": json.dumps(payload), "images": files},
            **_make_jwt(management),
        )
        assert response.status_code == 201
        prop = Property.objects.get(pk=response.json()["data"]["id"])
        assert VerificationVisit.objects.filter(property=prop).count() == 1

    def test_submit_requires_five_photos(self, api_client, management):
        district = DistrictFactory()
        owner = OwnerFactory()
        payload = {
            "engagement_type": "managed",
            "district_id": district.id,
            "owner_id": owner.id,
            "rooms": 2,
            "area_sqm": 50,
            "floor": 1,
            "total_floors": 5,
            "ask_price": "450.00",
        }
        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(2)]
        response = api_client.post(
            "/api/v1/properties/submit/",
            data={"payload": json.dumps(payload), "images": files},
            **_make_jwt(management),
        )
        assert response.status_code == 422

    def test_submit_rejects_invalid_floors(self, api_client, management):
        district = DistrictFactory()
        owner = OwnerFactory()
        payload = {
            "engagement_type": "managed",
            "district_id": district.id,
            "owner_id": owner.id,
            "rooms": 2,
            "area_sqm": 50,
            "floor": 7,
            "total_floors": 5,
            "ask_price": "450.00",
        }
        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(5)]
        response = api_client.post(
            "/api/v1/properties/submit/",
            data={"payload": json.dumps(payload), "images": files},
            **_make_jwt(management),
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestPropertyPhotos:
    def test_reorder_sets_cover(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.VACANT)
        _upload(api_client, management, prop.id, 6)
        photos = prop.photos.all()
        target = photos[1].id
        response = api_client.patch(
            f"/api/v1/properties/{prop.id}/photos/reorder/",
            data=json.dumps({"items": [{"id": target, "sort_order": 0, "is_primary": True, "caption": "Cover"}]}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        res_photos = response.json()["data"]["photos"]
        assert any(p["id"] == target and p["is_primary"] and p["caption"] == "Cover" for p in res_photos)

    @pytest.mark.parametrize("is_primary", [False, True])
    def test_reorder_requires_exactly_one_primary(self, api_client, management, is_primary):
        prop = PropertyFactory(status=PropertyStatus.PENDING_REVIEW)
        _upload(api_client, management, prop.id, 2)
        photos = list(prop.photos.order_by("id"))

        response = api_client.patch(
            f"/api/v1/properties/{prop.id}/photos/reorder/",
            data=json.dumps(
                {
                    "items": [
                        {"id": photos[0].id, "sort_order": 0, "is_primary": is_primary},
                        {"id": photos[1].id, "sort_order": 1, "is_primary": is_primary},
                    ]
                }
            ),
            content_type="application/json",
            **_make_jwt(management),
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "exactly_one_primary_photo_required"
        assert prop.photos.filter(is_primary=True).count() == 1

    def test_reorder_rejects_duplicate_photo_ids(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.PENDING_REVIEW)
        _upload(api_client, management, prop.id, 2)
        photo = prop.photos.first()

        response = api_client.patch(
            f"/api/v1/properties/{prop.id}/photos/reorder/",
            data=json.dumps(
                {
                    "items": [
                        {"id": photo.id, "sort_order": 0, "is_primary": True},
                        {"id": photo.id, "sort_order": 1, "is_primary": False},
                    ]
                }
            ),
            content_type="application/json",
            **_make_jwt(management),
        )

        assert response.status_code == 400
        assert response.json()["error"] == {"code": "duplicate_photo_ids", "photo_ids": [photo.id]}
        assert prop.photos.filter(is_primary=True).count() == 1

    def test_reorder_rejects_photo_from_another_property(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.PENDING_REVIEW)
        _upload(api_client, management, prop.id, 2)
        foreign_photo = PropertyPhotoFactory(property=PropertyFactory(status=PropertyStatus.PENDING_REVIEW))

        response = api_client.patch(
            f"/api/v1/properties/{prop.id}/photos/reorder/",
            data=json.dumps({"items": [{"id": foreign_photo.id, "sort_order": 0, "is_primary": True}]}),
            content_type="application/json",
            **_make_jwt(management),
        )

        assert response.status_code == 400
        assert response.json()["error"] == {
            "code": "invalid_property_photo_ids",
            "photo_ids": [foreign_photo.id],
        }
        assert prop.photos.filter(is_primary=True).count() == 1

    def test_delete_photo_enforces_five_minimum(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.VACANT)
        ListingFactory(property=prop, status=ListingStatus.PUBLISHED)
        _upload(api_client, management, prop.id, 5)
        photo = prop.photos.first()
        response = api_client.delete(
            f"/api/v1/properties/{prop.id}/photos/{photo.id}/",
            **_make_jwt(management),
        )
        assert response.status_code == 422

    def test_delete_photo_when_more_than_five(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.VACANT)
        _upload(api_client, management, prop.id, 7)
        photo = prop.photos.last()
        response = api_client.delete(
            f"/api/v1/properties/{prop.id}/photos/{photo.id}/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        assert Property.objects.get(pk=prop.id).photos.count() == 6

    def test_photos_require_management(self, api_client, owner):
        prop = PropertyFactory(status=PropertyStatus.VACANT)
        response = _upload(api_client, owner, prop.id, 1)
        assert response.status_code == 403


@pytest.mark.django_db
class TestVerificationVisits:
    def test_schedule_and_list(self, api_client, management):
        prop = PropertyFactory()
        when = (datetime.now(UTC) + timedelta(days=3)).isoformat()
        created = api_client.post(
            f"/api/v1/properties/{prop.id}/verification-visits/",
            data=json.dumps({"scheduled_for": when, "notes": "Bring keys"}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert created.status_code == 201
        listed = api_client.get(
            f"/api/v1/properties/{prop.id}/verification-visits/",
            **_make_jwt(management),
        )
        assert len(listed.json()["data"]) == 1
        assert listed.json()["data"][0]["notes"] == "Bring keys"

    def test_rejected_for_one_off_property(self, api_client, management):
        prop = PropertyFactory(engagement_type=PropertyEngagementType.ONE_OFF, owner=None)
        when = (datetime.now(UTC) + timedelta(days=3)).isoformat()
        response = api_client.post(
            f"/api/v1/properties/{prop.id}/verification-visits/",
            data=json.dumps({"scheduled_for": when}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 400
        assert response.json()["success"] is False
