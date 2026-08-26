import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.constants import InventoryActStatus, LeaseStatus
from tests.factories import (
    AgentFactory,
    InventoryActFactory,
    InventoryActItemFactory,
    LeaseFactory,
    OwnerFactory,
    PropertyFactory,
    TenantFactory,
    UserFactory,
)
from tests.integration.property.test_api import _make_jwt

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.django_db
class TestInventoryActLifecycle:
    def test_create_act_atomic_with_items_and_photos(self, api_client):
        mgmt = UserFactory()
        prop = PropertyFactory()
        photo = SimpleUploadedFile("room.png", _PNG, content_type="image/png")

        payload = {
            "property_id": prop.id,
            "act_type": "handover",
            "notes": "Move-in inspection",
            "items": [
                {"area": "Kitchen", "condition": "good", "notes": "Clean"},
                {"area": "Bathroom", "condition": "fair", "notes": "Minor leak"},
            ],
            "photo_item_map": {"0": 0},
            "captions": ["Kitchen sink"],
        }

        response = api_client.post(
            "/api/v1/inventory/acts/",
            data={"payload": json.dumps(payload), "images": [photo]},
            **_make_jwt(mgmt),
        )

        assert response.status_code == 201
        body = response.json()["data"]
        assert body["status"] == InventoryActStatus.FINALIZED
        assert body["created_by_id"] == mgmt.id
        assert len(body["items"]) == 2
        assert len(body["photos"]) == 1

    def test_agent_can_create(self, api_client):
        agent = AgentFactory()
        prop = PropertyFactory()
        payload = {
            "property_id": prop.id,
            "items": [{"area": "Living room", "condition": "good"}],
        }
        response = api_client.post(
            "/api/v1/inventory/acts/",
            data={"payload": json.dumps(payload)},
            **_make_jwt(agent),
        )
        assert response.status_code == 201

    def test_tenant_cannot_create(self, api_client):
        tenant = TenantFactory()
        prop = PropertyFactory()
        payload = {
            "property_id": prop.id,
            "items": [{"area": "Living room", "condition": "good"}],
        }
        response = api_client.post(
            "/api/v1/inventory/acts/",
            data={"payload": json.dumps(payload)},
            **_make_jwt(tenant),
        )
        assert response.status_code == 403

    def test_create_rejects_without_items(self, api_client):
        mgmt = UserFactory()
        prop = PropertyFactory()
        payload = {
            "property_id": prop.id,
            "items": [],
        }
        response = api_client.post(
            "/api/v1/inventory/acts/",
            data={"payload": json.dumps(payload)},
            **_make_jwt(mgmt),
        )
        assert response.status_code in (400, 422)

    def test_create_rejects_lease_from_another_property(self, api_client):
        mgmt = UserFactory()
        prop = PropertyFactory()
        lease = LeaseFactory(property=PropertyFactory())
        payload = {
            "property_id": prop.id,
            "lease_id": lease.id,
            "items": [{"area": "Living room", "condition": "good"}],
        }

        response = api_client.post(
            "/api/v1/inventory/acts/",
            data={"payload": json.dumps(payload)},
            **_make_jwt(mgmt),
        )

        assert response.status_code == 422
        assert response.json()["error"] == "Lease does not belong to the selected property."

    def test_acknowledge_act(self, api_client):
        mgmt = UserFactory()
        act = InventoryActFactory(created_by=mgmt)
        InventoryActItemFactory(act=act, area="Hallway")

        final_resp = api_client.post(
            f"/api/v1/inventory/acts/{act.id}/acknowledge/",
            data=json.dumps({"acknowledged_by_name": "John Tenant", "acknowledgment_note": "Agreed"}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert final_resp.status_code == 200
        act.refresh_from_db()
        assert act.status == InventoryActStatus.FINALIZED
        assert act.acknowledged_by_name == "John Tenant"
        assert act.acknowledgment_note == "Agreed"
        assert act.acknowledged_at is not None

    def test_acknowledge_act_cannot_overwrite_existing_acknowledgment(self, api_client):
        mgmt = UserFactory()
        acknowledged_at = timezone.now()
        act = InventoryActFactory(
            created_by=mgmt,
            acknowledged_by_name="Original Tenant",
            acknowledged_at=acknowledged_at,
        )
        InventoryActItemFactory(act=act, area="Hallway")

        response = api_client.post(
            f"/api/v1/inventory/acts/{act.id}/acknowledge/",
            data=json.dumps({"acknowledged_by_name": "Replacement Name", "acknowledgment_note": "Changed"}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )

        assert response.status_code == 409
        assert response.json()["error"] == {"code": "inventory_act_already_acknowledged"}
        act.refresh_from_db()
        assert act.acknowledged_by_name == "Original Tenant"
        assert act.acknowledged_at == acknowledged_at
        assert act.acknowledgment_note in (None, "")

    def test_upload_rejects_non_image(self, api_client):
        mgmt = UserFactory()
        prop = PropertyFactory()
        bad = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        payload = {
            "property_id": prop.id,
            "items": [{"area": "Living Room"}],
        }
        resp = api_client.post(
            "/api/v1/inventory/acts/",
            data={"payload": json.dumps(payload), "images": [bad]},
            **_make_jwt(mgmt),
        )
        assert resp.status_code == 422


@pytest.mark.django_db
class TestInventoryActAccess:
    def test_tenant_can_read_own_lease_act(self, api_client):
        tenant = TenantFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner)
        lease = LeaseFactory(tenant=tenant, property=prop, status=LeaseStatus.ACTIVE)
        act = InventoryActFactory(property=prop, lease=lease)
        InventoryActItemFactory(act=act, area="Room")

        resp = api_client.get(f"/api/v1/inventory/acts/{act.id}/", **_make_jwt(tenant))
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == act.id

    def test_tenant_cannot_read_other_act(self, api_client):
        tenant = TenantFactory()
        act = InventoryActFactory()
        InventoryActItemFactory(act=act, area="Room")

        resp = api_client.get(f"/api/v1/inventory/acts/{act.id}/", **_make_jwt(tenant))
        assert resp.status_code == 403

    def test_list_filter_by_property(self, api_client):
        mgmt = UserFactory()
        prop = PropertyFactory()
        acknowledged_at = timezone.now()
        act1 = InventoryActFactory(
            property=prop,
            acknowledged_by_name="Tenant Name",
            acknowledged_at=acknowledged_at,
        )
        InventoryActItemFactory(act=act1, area="Room")
        act2 = InventoryActFactory()
        InventoryActItemFactory(act=act2, area="Room")

        resp = api_client.get("/api/v1/inventory/acts/", data={"property_id": prop.id}, **_make_jwt(mgmt))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["property_id"] == prop.id
        assert data[0]["acknowledged_by_name"] == "Tenant Name"
        assert data[0]["acknowledged_at"] is not None

    def test_requires_auth(self, api_client):
        resp = api_client.get("/api/v1/inventory/acts/")
        assert resp.status_code == 401


@pytest.mark.django_db
class TestInventoryActStatsAndAwaitingAck:
    def test_awaiting_ack_filter(self, api_client):
        mgmt = UserFactory()
        awaiting = InventoryActFactory(status=InventoryActStatus.FINALIZED, acknowledged_at=None)
        InventoryActItemFactory(act=awaiting, area="Room")
        ack = InventoryActFactory(
            status=InventoryActStatus.FINALIZED,
            acknowledged_at=timezone.now(),
            acknowledged_by_name="Tenant T.",
        )
        InventoryActItemFactory(act=ack, area="Room")

        response = api_client.get("/api/v1/inventory/acts/?awaiting_ack=true", **_make_jwt(mgmt))
        assert response.status_code == 200
        rows = response.json()["data"]
        assert [r["id"] for r in rows] == [awaiting.id]

    def test_stats_counts(self, api_client):
        mgmt = UserFactory()
        act1 = InventoryActFactory(status=InventoryActStatus.FINALIZED, acknowledged_at=None)
        InventoryActItemFactory(act=act1, area="Room")
        act2 = InventoryActFactory(status=InventoryActStatus.FINALIZED, acknowledged_at=timezone.now())
        InventoryActItemFactory(act=act2, area="Room")

        response = api_client.get("/api/v1/inventory/acts/stats/", **_make_jwt(mgmt))
        assert response.status_code == 200
        counts = response.json()["data"]["counts"]
        assert counts == {"finalized": 2, "awaiting_ack": 1, "all": 2}
