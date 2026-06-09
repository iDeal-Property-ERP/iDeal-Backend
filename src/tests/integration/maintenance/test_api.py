import json

import pytest
from django.conf import settings

from core.constants import ServiceRequestPriority, ServiceRequestStatus
from tests.factories import ServiceRequestFactory


def _make_jwt(user):
    from datetime import UTC, datetime, timedelta

    import jwt

    payload = {
        "sub": str(user.id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "token_type": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.mark.django_db
class TestServiceRequestAPI:
    def test_create_request(self, api_client, tenant, property_obj):
        payload = json.dumps(
            {
                "property_id": property_obj.id,
                "tenant_id": tenant.id,
                "title": "Broken sink",
                "description": "Sink in the kitchen is leaking.",
                "priority": "medium",
            }
        )
        response = api_client.post(
            "/api/v1/maintenance/requests/",
            payload,
            content_type="application/json",
            **_make_jwt(tenant),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["title"] == "Broken sink"
        assert body["data"]["status"] == "open"
        assert body["data"]["property_id"] == property_obj.id
        assert body["data"]["tenant_id"] == tenant.id

    def test_create_request_requires_auth(self, api_client, tenant, property_obj):
        payload = json.dumps(
            {
                "property_id": property_obj.id,
                "tenant_id": tenant.id,
                "title": "Broken sink",
                "description": "Sink in the kitchen is leaking.",
            }
        )
        response = api_client.post(
            "/api/v1/maintenance/requests/",
            payload,
            content_type="application/json",
        )
        assert response.status_code in (401, 403)

    def test_list_requests(self, api_client, owner):
        ServiceRequestFactory()
        ServiceRequestFactory()
        response = api_client.get(
            "/api/v1/maintenance/requests/",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 2

    def test_list_requests_requires_auth(self, api_client):
        response = api_client.get("/api/v1/maintenance/requests/")
        assert response.status_code in (401, 403)

    def test_list_requests_filter_by_status(self, api_client, owner):
        ServiceRequestFactory(status=ServiceRequestStatus.OPEN)
        ServiceRequestFactory(status=ServiceRequestStatus.IN_PROGRESS)
        ServiceRequestFactory(status=ServiceRequestStatus.OPEN)
        response = api_client.get(
            "/api/v1/maintenance/requests/?status=open",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        for item in body["data"]:
            assert item["status"] == "open"

    def test_list_requests_filter_by_property(self, api_client, owner, property_obj):
        from tests.factories import PropertyFactory

        other_property = PropertyFactory()
        ServiceRequestFactory(property=property_obj)
        ServiceRequestFactory(property=other_property)
        response = api_client.get(
            f"/api/v1/maintenance/requests/?property_id={property_obj.id}",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        for item in body["data"]:
            assert item["property_id"] == property_obj.id

    def test_list_requests_paginated(self, api_client, owner):
        for _ in range(5):
            ServiceRequestFactory()
        response = api_client.get(
            "/api/v1/maintenance/requests/?page=1&per_page=3",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["per_page"] == 3
        assert data["page"]["number"] == 1
        assert len(data["page"]["object_list"]) == 3

    def test_retrieve_request(self, api_client, owner):
        req = ServiceRequestFactory()
        response = api_client.get(
            f"/api/v1/maintenance/requests/{req.id}/",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["id"] == req.id
        assert body["data"]["title"] == req.title

    def test_retrieve_request_404(self, api_client, owner):
        response = api_client.get(
            "/api/v1/maintenance/requests/99999/",
            **_make_jwt(owner),
        )
        assert response.status_code == 404

    def test_partial_update_request(self, api_client, owner):
        req = ServiceRequestFactory(title="Old title", priority=ServiceRequestPriority.LOW)
        payload = json.dumps({"title": "New title", "priority": "high"})
        response = api_client.patch(
            f"/api/v1/maintenance/requests/{req.id}/",
            payload,
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["title"] == "New title"
        assert body["data"]["priority"] == "high"

        req.refresh_from_db()
        assert req.title == "New title"

    def test_assign_request(self, api_client, owner):
        from tests.factories import UserFactory

        req = ServiceRequestFactory(status=ServiceRequestStatus.OPEN)
        staff = UserFactory()
        payload = json.dumps({"assigned_to_id": staff.id})
        response = api_client.post(
            f"/api/v1/maintenance/requests/{req.id}/assign/",
            payload,
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["assigned_to_id"] == staff.id
        assert body["data"]["status"] == "in_progress"

        req.refresh_from_db()
        assert req.assigned_to == staff
        assert req.status == ServiceRequestStatus.IN_PROGRESS

    def test_assign_request_404(self, api_client, owner):
        payload = json.dumps({"assigned_to_id": 1})
        response = api_client.post(
            "/api/v1/maintenance/requests/99999/assign/",
            payload,
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 404

    def test_resolve_request(self, api_client, owner):
        from decimal import Decimal

        req = ServiceRequestFactory(status=ServiceRequestStatus.IN_PROGRESS)
        payload = json.dumps({"cost": "150.00", "resolution_notes": "Fixed the pipe"})
        response = api_client.post(
            f"/api/v1/maintenance/requests/{req.id}/resolve/",
            payload,
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "resolved"
        assert body["data"]["cost"] == "150.00"
        assert body["data"]["resolution_notes"] == "Fixed the pipe"

        req.refresh_from_db()
        assert req.status == ServiceRequestStatus.RESOLVED
        assert req.cost == Decimal("150.00")

    def test_resolve_request_404(self, api_client, owner):
        payload = json.dumps({"cost": "150.00", "resolution_notes": "Fixed"})
        response = api_client.post(
            "/api/v1/maintenance/requests/99999/resolve/",
            payload,
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 404

    def test_invalid_create_request_data(self, api_client, tenant):
        payload = json.dumps({"property_id": 1})
        response = api_client.post(
            "/api/v1/maintenance/requests/",
            payload,
            content_type="application/json",
            **_make_jwt(tenant),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert "error" in body

    def test_resolve_requires_auth(self, api_client, owner):
        req = ServiceRequestFactory(status=ServiceRequestStatus.IN_PROGRESS)
        payload = json.dumps({"cost": "150.00", "resolution_notes": "Fixed"})
        response = api_client.post(
            f"/api/v1/maintenance/requests/{req.id}/resolve/",
            payload,
            content_type="application/json",
        )
        assert response.status_code in (401, 403)

    def test_assign_requires_auth(self, api_client, owner):
        from tests.factories import UserFactory

        req = ServiceRequestFactory(status=ServiceRequestStatus.OPEN)
        staff = UserFactory()
        payload = json.dumps({"assigned_to_id": staff.id})
        response = api_client.post(
            f"/api/v1/maintenance/requests/{req.id}/assign/",
            payload,
            content_type="application/json",
        )
        assert response.status_code in (401, 403)
