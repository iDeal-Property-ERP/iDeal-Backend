from datetime import UTC, datetime, timedelta

import jwt
import pytest
from django.conf import settings

from core.constants import BookingStatus, UserRole, ViewingRequestStatus, ViewingTimeSlot
from tests.factories import (
    BookingFactory,
    UserFactory,
    ViewingRequestFactory,
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
class TestManagementLeadsAPI:
    def test_requires_management_role(self, api_client):
        tenant = UserFactory(role=UserRole.TENANT)
        resp = api_client.get("/api/v1/management/leads/", **_make_jwt(tenant))
        assert resp.status_code in (401, 403)

    def test_merges_viewings_and_bookings(self, api_client):
        ViewingRequestFactory(status=ViewingRequestStatus.PENDING)
        BookingFactory(status=BookingStatus.REQUESTED)
        resp = api_client.get("/api/v1/management/leads/", **_make_jwt(_mgmt()))
        assert resp.status_code == 200
        rows = resp.json()["data"]
        assert len(rows) == 2
        types = {r["type"] for r in rows}
        assert types == {"viewing", "booking"}
        # composite id form
        assert all(r["id"].startswith(("v-", "b-")) for r in rows)

    def test_tab_new_buckets_pending_and_requested(self, api_client):
        ViewingRequestFactory(status=ViewingRequestStatus.PENDING)
        ViewingRequestFactory(status=ViewingRequestStatus.CONFIRMED)
        BookingFactory(status=BookingStatus.REQUESTED)
        BookingFactory(status=BookingStatus.APPROVED)
        resp = api_client.get("/api/v1/management/leads/?tab=new", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 2

    def test_tab_scheduled_only_confirmed_viewings(self, api_client):
        ViewingRequestFactory(status=ViewingRequestStatus.CONFIRMED)
        BookingFactory(status=BookingStatus.APPROVED)
        resp = api_client.get("/api/v1/management/leads/?tab=scheduled", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["type"] == "viewing"

    def test_tab_awaiting_only_approved_bookings(self, api_client):
        BookingFactory(status=BookingStatus.APPROVED)
        ViewingRequestFactory(status=ViewingRequestStatus.PENDING)
        resp = api_client.get("/api/v1/management/leads/?tab=awaiting", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["type"] == "booking"

    def test_tab_closed_includes_converted(self, api_client):
        BookingFactory(status=BookingStatus.CONVERTED)
        BookingFactory(status=BookingStatus.REJECTED)
        ViewingRequestFactory(status=ViewingRequestStatus.CANCELLED)
        resp = api_client.get("/api/v1/management/leads/?tab=closed", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 3

    def test_type_filter_excludes_other_source(self, api_client):
        ViewingRequestFactory(status=ViewingRequestStatus.PENDING)
        BookingFactory(status=BookingStatus.REQUESTED)
        resp = api_client.get("/api/v1/management/leads/?type=viewing", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["type"] == "viewing"

    def test_search_matches_viewing_name(self, api_client):
        ViewingRequestFactory(full_name="Dilnoza Mirzaeva", status=ViewingRequestStatus.PENDING)
        ViewingRequestFactory(full_name="Someone Else", status=ViewingRequestStatus.PENDING)
        resp = api_client.get("/api/v1/management/leads/?search=Dilnoza", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["name"] == "Dilnoza Mirzaeva"

    def test_pagination_shape(self, api_client):
        for _ in range(3):
            ViewingRequestFactory(status=ViewingRequestStatus.PENDING)
        resp = api_client.get("/api/v1/management/leads/?page=1&per_page=2", **_make_jwt(_mgmt()))
        data = resp.json()["data"]
        assert data["count"] == 3
        assert data["num_pages"] == 2
        assert len(data["page"]["object_list"]) == 2

    def test_stats_counts(self, api_client):
        ViewingRequestFactory(status=ViewingRequestStatus.PENDING)
        BookingFactory(status=BookingStatus.REQUESTED)
        BookingFactory(status=BookingStatus.APPROVED)
        resp = api_client.get("/api/v1/management/leads/stats/", **_make_jwt(_mgmt()))
        data = resp.json()["data"]
        assert data["counts"]["new"] == 2
        assert data["counts"]["awaiting"] == 1
        assert data["counts"]["all"] == 3
        assert data["open"] == 2
        assert data["by_type"] == {"viewing": 1, "booking": 2}

    def test_propose_time_updates_slot(self, api_client):
        vr = ViewingRequestFactory(status=ViewingRequestStatus.PENDING)
        resp = api_client.post(
            f"/api/v1/management/viewing-requests/{vr.id}/propose-time/",
            data={"preferred_date": "2026-08-01", "preferred_time": ViewingTimeSlot.T_15},
            content_type="application/json",
            **_make_jwt(_mgmt()),
        )
        assert resp.status_code == 200
        vr.refresh_from_db()
        assert str(vr.preferred_date) == "2026-08-01"
        assert vr.preferred_time == ViewingTimeSlot.T_15

    def test_propose_time_confirmed_resets_to_pending(self, api_client):
        vr = ViewingRequestFactory(status=ViewingRequestStatus.CONFIRMED)
        resp = api_client.post(
            f"/api/v1/management/viewing-requests/{vr.id}/propose-time/",
            data={"preferred_date": "2026-08-02", "preferred_time": ViewingTimeSlot.T_10},
            content_type="application/json",
            **_make_jwt(_mgmt()),
        )
        assert resp.status_code == 200
        vr.refresh_from_db()
        assert vr.status == ViewingRequestStatus.PENDING

    def test_propose_time_rejects_cancelled(self, api_client):
        vr = ViewingRequestFactory(status=ViewingRequestStatus.CANCELLED)
        resp = api_client.post(
            f"/api/v1/management/viewing-requests/{vr.id}/propose-time/",
            data={"preferred_date": "2026-08-02"},
            content_type="application/json",
            **_make_jwt(_mgmt()),
        )
        assert resp.status_code == 400

    def test_propose_time_rejects_bad_slot(self, api_client):
        vr = ViewingRequestFactory(status=ViewingRequestStatus.PENDING)
        resp = api_client.post(
            f"/api/v1/management/viewing-requests/{vr.id}/propose-time/",
            data={"preferred_date": "2026-08-02", "preferred_time": "99:99"},
            content_type="application/json",
            **_make_jwt(_mgmt()),
        )
        assert resp.status_code == 400
