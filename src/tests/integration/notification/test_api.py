import pytest

from core.constants import NotificationType
from tests.factories import NotificationFactory, TenantFactory
from tests.integration.property.test_api import _make_jwt


@pytest.mark.django_db
class TestNotificationAPI:
    def test_list_only_own_notifications(self, api_client):
        user = TenantFactory()
        other = TenantFactory()
        NotificationFactory(recipient=user, title="Mine")
        NotificationFactory(recipient=other, title="Theirs")

        response = api_client.get("/api/v1/notifications/", **_make_jwt(user))

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        titles = [n["title"] for n in body["data"]]
        assert "Mine" in titles
        assert "Theirs" not in titles

    def test_unread_count(self, api_client):
        user = TenantFactory()
        NotificationFactory(recipient=user, is_read=False)
        NotificationFactory(recipient=user, is_read=False)
        NotificationFactory(recipient=user, is_read=True)

        response = api_client.get("/api/v1/notifications/unread-count/", **_make_jwt(user))

        assert response.status_code == 200
        assert response.json()["data"]["unread_count"] == 2

    def test_mark_read(self, api_client):
        user = TenantFactory()
        notification = NotificationFactory(recipient=user, is_read=False)

        response = api_client.post(f"/api/v1/notifications/{notification.id}/read/", **_make_jwt(user))

        assert response.status_code == 200
        notification.refresh_from_db()
        assert notification.is_read is True
        assert notification.read_at is not None

    def test_cannot_mark_read_other_users_notification(self, api_client):
        user = TenantFactory()
        other = TenantFactory()
        notification = NotificationFactory(recipient=other, is_read=False)

        response = api_client.post(f"/api/v1/notifications/{notification.id}/read/", **_make_jwt(user))

        assert response.status_code == 404

    def test_read_all(self, api_client):
        user = TenantFactory()
        NotificationFactory(recipient=user, is_read=False)
        NotificationFactory(recipient=user, is_read=False)

        response = api_client.post("/api/v1/notifications/read-all/", **_make_jwt(user))

        assert response.status_code == 200
        assert response.json()["data"]["updated"] == 2

    def test_requires_auth(self, api_client):
        response = api_client.get("/api/v1/notifications/")
        assert response.status_code == 401

    def test_notify_service_creates_notification(self):
        from notification.services import notify

        user = TenantFactory()
        notification = notify(
            recipient=user,
            type=NotificationType.GENERAL,
            title="Hello",
            body="World",
        )
        assert notification.id is not None
        assert notification.recipient_id == user.id
        assert notification.is_read is False
