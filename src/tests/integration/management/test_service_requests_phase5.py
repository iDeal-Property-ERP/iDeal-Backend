from datetime import UTC, datetime, timedelta

import jwt
import pytest
from django.conf import settings
from django.utils import timezone
from maintenance.models import ServiceRequestComment

from core.constants import CostBearer, ServiceRequestPriority, ServiceRequestStatus, UserRole
from tests.factories import (
    ServiceRequestCommentFactory,
    ServiceRequestFactory,
    UserFactory,
)


def _make_jwt(user):
    payload = {
        "sub": str(user.id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "token_type": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _mgmt():
    return UserFactory(role=UserRole.MANAGEMENT)


@pytest.mark.django_db
class TestManagementServiceRequestsPhase5:
    def test_search_and_unassigned_filter(self, api_client):
        ServiceRequestFactory(title="No heating boiler", assigned_to=None)
        ServiceRequestFactory(title="AC not cooling", assigned_to=UserFactory(role=UserRole.MANAGEMENT))
        resp = api_client.get("/api/v1/management/service-requests/?unassigned=true", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["title"] == "No heating boiler"

    def test_order_by_priority(self, api_client):
        ServiceRequestFactory(priority=ServiceRequestPriority.LOW)
        ServiceRequestFactory(priority=ServiceRequestPriority.CRITICAL)
        ServiceRequestFactory(priority=ServiceRequestPriority.MEDIUM)
        resp = api_client.get("/api/v1/management/service-requests/?order=priority", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert rows[0]["priority"] == ServiceRequestPriority.CRITICAL
        assert rows[-1]["priority"] == ServiceRequestPriority.LOW

    def test_output_has_new_fields(self, api_client):
        ServiceRequestFactory()
        resp = api_client.get("/api/v1/management/service-requests/", **_make_jwt(_mgmt()))
        row = resp.json()["data"][0]
        assert "photos_count" in row
        assert "photo_urls" in row
        assert "resolved_at" in row
        assert "cost_bearer" in row

    def test_stats_cost_split_null_bearer_is_platform(self, api_client):
        now = timezone.now()
        ServiceRequestFactory(
            status=ServiceRequestStatus.RESOLVED, cost=100, cost_bearer=CostBearer.OWNER, resolved_at=now
        )
        ServiceRequestFactory(status=ServiceRequestStatus.RESOLVED, cost=50, cost_bearer=None, resolved_at=now)
        ServiceRequestFactory(status=ServiceRequestStatus.OPEN, assigned_to=None)
        resp = api_client.get("/api/v1/management/service-requests/stats/", **_make_jwt(_mgmt()))
        data = resp.json()["data"]
        assert data["cost_30d_total"] == "150.00"
        assert data["cost_30d_owner"] == "100.00"
        assert data["cost_30d_platform"] == "50.00"
        assert data["open"] == 1
        assert data["open_unassigned"] == 1

    def test_cancel_without_body(self, api_client):
        sr = ServiceRequestFactory(status=ServiceRequestStatus.OPEN)
        resp = api_client.post(f"/api/v1/management/service-requests/{sr.id}/cancel/", **_make_jwt(_mgmt()))
        assert resp.status_code == 200
        sr.refresh_from_db()
        assert sr.status == ServiceRequestStatus.CANCELLED

    def test_cancel_with_reason_body(self, api_client):
        sr = ServiceRequestFactory(status=ServiceRequestStatus.OPEN)
        resp = api_client.post(
            f"/api/v1/management/service-requests/{sr.id}/cancel/",
            data={"reason": "Duplicate of SRQ-100"},
            content_type="application/json",
            **_make_jwt(_mgmt()),
        )
        assert resp.status_code == 200
        sr.refresh_from_db()
        assert "Duplicate of SRQ-100" in sr.resolution_notes

    def test_cancel_rejects_resolved(self, api_client):
        sr = ServiceRequestFactory(status=ServiceRequestStatus.RESOLVED)
        resp = api_client.post(f"/api/v1/management/service-requests/{sr.id}/cancel/", **_make_jwt(_mgmt()))
        assert resp.status_code == 400

    def test_comments_list_and_create(self, api_client):
        sr = ServiceRequestFactory()
        ServiceRequestCommentFactory(service_request=sr, body="Existing note")
        mgmt = _mgmt()
        # list
        resp = api_client.get(f"/api/v1/management/service-requests/{sr.id}/comments/", **_make_jwt(mgmt))
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1
        # create
        resp = api_client.post(
            f"/api/v1/management/service-requests/{sr.id}/comments/",
            data={"body": "Valve in stock"},
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert resp.status_code == 201
        assert ServiceRequestComment.objects.filter(service_request=sr, body="Valve in stock").exists()

    def test_resolve_sets_resolved_at_and_bearer(self, api_client):
        sr = ServiceRequestFactory(status=ServiceRequestStatus.IN_PROGRESS)
        resp = api_client.post(
            f"/api/v1/maintenance/requests/{sr.id}/resolve/",
            data={"cost": "75.00", "resolution_notes": "Fixed", "cost_bearer": CostBearer.OWNER},
            content_type="application/json",
            **_make_jwt(_mgmt()),
        )
        assert resp.status_code == 200
        sr.refresh_from_db()
        assert sr.status == ServiceRequestStatus.RESOLVED
        assert sr.resolved_at is not None
        assert sr.cost_bearer == CostBearer.OWNER

    def test_queue_counts(self, api_client):
        ServiceRequestFactory(status=ServiceRequestStatus.OPEN)
        resp = api_client.get("/api/v1/management/queue-counts/", **_make_jwt(_mgmt()))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert set(data.keys()) == {"leads", "onboardings", "maintenance", "payments", "payouts"}
        assert data["maintenance"] == 1
