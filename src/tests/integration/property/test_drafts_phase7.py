import json
from datetime import UTC, datetime, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from property.models import Property, VerificationVisit

from core.constants import PropertyStatus
from tests.factories import PropertyFactory
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
class TestPropertyDrafts:
    def test_create_draft_minimal(self, api_client, management):
        response = api_client.post(
            "/api/v1/properties/drafts/",
            data=json.dumps({"name": "Chilonzor Sunrise 9-3"}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["status"] == PropertyStatus.DRAFT
        assert data["name"] == "Chilonzor Sunrise 9-3"
        assert data["district"] is None
        assert data["ask_price"] is None

    def test_create_draft_defaults_name(self, api_client, management):
        response = api_client.post(
            "/api/v1/properties/drafts/",
            data=json.dumps({}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 201
        assert response.json()["data"]["name"] == "Untitled property"

    def test_autosave_patch_partial(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.DRAFT, name="Draft A")
        response = api_client.patch(
            f"/api/v1/properties/{prop.id}/",
            data=json.dumps({"rooms": 3, "ask_price": "480.00"}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        prop.refresh_from_db()
        assert prop.rooms == 3
        assert str(prop.ask_price) == "480.00"
        assert prop.status == PropertyStatus.DRAFT

    def test_publish_incomplete_returns_missing_codes(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.DRAFT, district=None, ask_price=None)
        response = api_client.post(
            f"/api/v1/properties/{prop.id}/publish/",
            data=json.dumps({}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "incomplete"
        assert "district" in error["missing"]
        assert "ask_price" in error["missing"]
        assert "photos" in error["missing"]

    def test_publish_complete_goes_vacant(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.DRAFT)
        _upload(api_client, management, prop.id, 5)
        response = api_client.post(
            f"/api/v1/properties/{prop.id}/publish/",
            data=json.dumps({}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        prop.refresh_from_db()
        assert prop.status == PropertyStatus.VACANT

    def test_publish_schedules_verification(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.DRAFT)
        _upload(api_client, management, prop.id, 5)
        when = (datetime.now(UTC) + timedelta(days=2)).isoformat()
        response = api_client.post(
            f"/api/v1/properties/{prop.id}/publish/",
            data=json.dumps({"schedule_verification_at": when}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        assert VerificationVisit.objects.filter(property=prop).count() == 1
        assert response.json()["data"]["verification"] is not None

    def test_double_publish_rejected(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.VACANT)
        response = api_client.post(
            f"/api/v1/properties/{prop.id}/publish/",
            data=json.dumps({}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 400

    def test_owner_list_excludes_drafts(self, api_client, owner):
        PropertyFactory(owner=owner, status=PropertyStatus.DRAFT, name="Hidden draft")
        PropertyFactory(owner=owner, status=PropertyStatus.VACANT, name="Visible")
        response = api_client.get("/api/v1/properties/", **_make_jwt(owner))
        names = [p["name"] for p in response.json()["data"]]
        assert "Visible" in names
        assert "Hidden draft" not in names

    def test_management_workbench_excludes_drafts_by_default(self, api_client, management):
        PropertyFactory(status=PropertyStatus.DRAFT, name="Draft X")
        PropertyFactory(status=PropertyStatus.VACANT, name="Live X")
        response = api_client.get("/api/v1/management/properties/", **_make_jwt(management))
        names = [p["name"] for p in response.json()["data"]]
        assert "Live X" in names
        assert "Draft X" not in names

    def test_management_draft_tab_lists_drafts(self, api_client, management):
        PropertyFactory(status=PropertyStatus.DRAFT, name="Draft Y")
        response = api_client.get("/api/v1/management/properties/?status=draft", **_make_jwt(management))
        names = [p["name"] for p in response.json()["data"]]
        assert names == ["Draft Y"]

    def test_draft_tab_lists_incomplete_draft(self, api_client, management):
        # A draft created via the endpoint has null district/owner/prices — the
        # management list serializer must tolerate them (regression: 500).
        api_client.post(
            "/api/v1/properties/drafts/",
            data=json.dumps({"name": "Bare Draft"}),
            content_type="application/json",
            **_make_jwt(management),
        )
        response = api_client.get("/api/v1/management/properties/?status=draft", **_make_jwt(management))
        assert response.status_code == 200
        rows = response.json()["data"]
        row = next(r for r in rows if r["name"] == "Bare Draft")
        assert row["district_name"] is None
        assert row["owner_name"] is None
        assert row["rooms"] is None
        assert row["ask_price"] is None

    def test_publish_requires_address(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.DRAFT, address="")
        _upload(api_client, management, prop.id, 5)
        response = api_client.post(
            f"/api/v1/properties/{prop.id}/publish/",
            data=json.dumps({}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 422
        assert "address" in response.json()["error"]["missing"]


@pytest.mark.django_db
class TestPropertyPhotos:
    def test_upload_sets_first_primary(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.DRAFT)
        response = _upload(api_client, management, prop.id, 3)
        assert response.status_code == 201
        photos = response.json()["data"]["photos"]
        assert len(photos) == 3
        primaries = [p for p in photos if p["is_primary"]]
        assert len(primaries) == 1

    def test_reorder_sets_cover(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.DRAFT)
        uploaded = _upload(api_client, management, prop.id, 2).json()["data"]["photos"]
        target = uploaded[1]["id"]
        response = api_client.patch(
            f"/api/v1/properties/{prop.id}/photos/reorder/",
            data=json.dumps({"items": [{"id": target, "sort_order": 0, "is_primary": True, "caption": "Cover"}]}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        photos = response.json()["data"]["photos"]
        assert any(p["id"] == target and p["is_primary"] and p["caption"] == "Cover" for p in photos)

    def test_delete_photo(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.DRAFT)
        uploaded = _upload(api_client, management, prop.id, 2).json()["data"]["photos"]
        response = api_client.delete(
            f"/api/v1/properties/{prop.id}/photos/{uploaded[0]['id']}/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        assert Property.objects.get(pk=prop.id).photos.count() == 1

    def test_deleting_cover_promotes_next_photo(self, api_client, management):
        prop = PropertyFactory(status=PropertyStatus.DRAFT)
        uploaded = _upload(api_client, management, prop.id, 3).json()["data"]["photos"]
        cover = next(p for p in uploaded if p["is_primary"])
        response = api_client.delete(
            f"/api/v1/properties/{prop.id}/photos/{cover['id']}/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        remaining = response.json()["data"]["photos"]
        assert len(remaining) == 2
        assert sum(1 for p in remaining if p["is_primary"]) == 1

    def test_photos_require_management(self, api_client, owner):
        prop = PropertyFactory(status=PropertyStatus.DRAFT)
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
