import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.constants import InventoryActStatus, LeaseStatus
from tests.factories import (
    AgentFactory,
    InventoryActFactory,
    LeaseFactory,
    OwnerFactory,
    PropertyFactory,
    TenantFactory,
    UserFactory,
)
from tests.integration.property.test_api import _make_jwt

# 1x1 transparent PNG
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.django_db
class TestInventoryActLifecycle:
    def test_create_draft(self, api_client):
        mgmt = UserFactory()
        prop = PropertyFactory()

        response = api_client.post(
            "/api/v1/inventory/acts/",
            data=json.dumps({"property_id": prop.id, "act_type": "handover"}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )

        assert response.status_code in (200, 201)
        body = response.json()["data"]
        assert body["status"] == InventoryActStatus.DRAFT
        assert body["created_by_id"] == mgmt.id

    def test_agent_can_create(self, api_client):
        agent = AgentFactory()
        prop = PropertyFactory()
        response = api_client.post(
            "/api/v1/inventory/acts/",
            data=json.dumps({"property_id": prop.id}),
            content_type="application/json",
            **_make_jwt(agent),
        )
        assert response.status_code in (200, 201)

    def test_tenant_cannot_create(self, api_client):
        tenant = TenantFactory()
        prop = PropertyFactory()
        response = api_client.post(
            "/api/v1/inventory/acts/",
            data=json.dumps({"property_id": prop.id}),
            content_type="application/json",
            **_make_jwt(tenant),
        )
        assert response.status_code == 403

    def test_add_items_and_upload_photo_and_finalize(self, api_client):
        mgmt = UserFactory()
        act = InventoryActFactory(created_by=mgmt)

        # Add items (bulk replace)
        items_resp = api_client.post(
            f"/api/v1/inventory/acts/{act.id}/items/",
            data=json.dumps(
                {"items": [{"area": "Kitchen", "condition": "good"}, {"area": "Bathroom", "condition": "fair"}]}
            ),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert items_resp.status_code == 200
        assert len(items_resp.json()["data"]["items"]) == 2

        # Upload a photo (multipart)
        photo = SimpleUploadedFile("room.png", _PNG, content_type="image/png")
        photo_resp = api_client.post(
            f"/api/v1/inventory/acts/{act.id}/photos/",
            data={"images": photo},
            **_make_jwt(mgmt),
        )
        assert photo_resp.status_code in (200, 201)
        assert len(photo_resp.json()["data"]) == 1
        assert photo_resp.json()["data"][0]["image_url"]

        # Finalize
        final_resp = api_client.post(
            f"/api/v1/inventory/acts/{act.id}/finalize/",
            data=json.dumps({"acknowledged_by_name": "John Tenant"}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert final_resp.status_code == 200
        act.refresh_from_db()
        assert act.status == InventoryActStatus.FINALIZED
        assert act.acknowledged_by_name == "John Tenant"

    def test_finalized_act_is_immutable(self, api_client):
        mgmt = UserFactory()
        act = InventoryActFactory(created_by=mgmt, status=InventoryActStatus.FINALIZED)

        resp = api_client.post(
            f"/api/v1/inventory/acts/{act.id}/items/",
            data=json.dumps({"items": [{"area": "X"}]}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_upload_rejects_non_image(self, api_client):
        mgmt = UserFactory()
        act = InventoryActFactory(created_by=mgmt)
        bad = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        resp = api_client.post(
            f"/api/v1/inventory/acts/{act.id}/photos/",
            data={"images": bad},
            **_make_jwt(mgmt),
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestInventoryActAccess:
    def test_tenant_can_read_own_lease_act(self, api_client):
        tenant = TenantFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner)
        lease = LeaseFactory(tenant=tenant, property=prop, status=LeaseStatus.ACTIVE)
        act = InventoryActFactory(property=prop, lease=lease)

        resp = api_client.get(f"/api/v1/inventory/acts/{act.id}/", **_make_jwt(tenant))
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == act.id

    def test_tenant_cannot_read_other_act(self, api_client):
        tenant = TenantFactory()
        act = InventoryActFactory()  # no lease

        resp = api_client.get(f"/api/v1/inventory/acts/{act.id}/", **_make_jwt(tenant))
        assert resp.status_code == 403

    def test_list_filter_by_property(self, api_client):
        mgmt = UserFactory()
        prop = PropertyFactory()
        InventoryActFactory(property=prop)
        InventoryActFactory()

        resp = api_client.get("/api/v1/inventory/acts/", data={"property_id": prop.id}, **_make_jwt(mgmt))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["property_id"] == prop.id

    def test_requires_auth(self, api_client):
        resp = api_client.get("/api/v1/inventory/acts/")
        assert resp.status_code == 401


@pytest.mark.django_db
class TestInventoryActStatsAndAwaitingAck:
    def test_awaiting_ack_filter(self, api_client):
        from django.utils import timezone

        mgmt = UserFactory()
        InventoryActFactory(status=InventoryActStatus.DRAFT)
        awaiting = InventoryActFactory(status=InventoryActStatus.FINALIZED, acknowledged_at=None)
        InventoryActFactory(
            status=InventoryActStatus.FINALIZED,
            acknowledged_at=timezone.now(),
            acknowledged_by_name="Tenant T.",
        )

        response = api_client.get("/api/v1/inventory/acts/?awaiting_ack=true", **_make_jwt(mgmt))
        assert response.status_code == 200
        rows = response.json()["data"]
        assert [r["id"] for r in rows] == [awaiting.id]

    def test_stats_counts(self, api_client):
        from django.utils import timezone

        mgmt = UserFactory()
        InventoryActFactory(status=InventoryActStatus.DRAFT)
        InventoryActFactory(status=InventoryActStatus.FINALIZED, acknowledged_at=None)
        InventoryActFactory(status=InventoryActStatus.FINALIZED, acknowledged_at=timezone.now())

        response = api_client.get("/api/v1/inventory/acts/stats/", **_make_jwt(mgmt))
        assert response.status_code == 200
        counts = response.json()["data"]["counts"]
        assert counts == {"draft": 1, "finalized": 2, "awaiting_ack": 1, "all": 3}
