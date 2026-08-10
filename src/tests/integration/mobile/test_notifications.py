import json

import pytest
from notification.models import DeviceToken, NotificationPreference

from core.constants import NotificationAudience, NotificationCategory, NotificationType
from tests.factories import DeviceTokenFactory, NotificationFactory, TenantFactory
from tests.integration.property.test_api import _make_jwt


def _post(api_client, path, payload, **headers):
    return api_client.post(path, data=json.dumps(payload), content_type="application/json", **headers)


def _patch(api_client, path, payload, **headers):
    return api_client.patch(path, data=json.dumps(payload), content_type="application/json", **headers)


@pytest.mark.django_db
class TestMobileNotificationsAPI:
    list_url = "/api/v1/mobile/notifications/"

    def test_list_is_paginated_and_scoped_to_mobile_audiences(self, api_client):
        user = TenantFactory()
        other = TenantFactory()
        mobile = NotificationFactory(
            recipient=user,
            audience=NotificationAudience.MOBILE,
            type=NotificationType.PAYMENT_DUE,
            title="Mobile",
        )
        both = NotificationFactory(recipient=user, audience=NotificationAudience.BOTH, title="Both")
        NotificationFactory(recipient=user, audience=NotificationAudience.ERP, title="ERP")
        NotificationFactory(recipient=other, audience=NotificationAudience.BOTH, title="Other")

        response = api_client.get(
            self.list_url,
            {"page": 1, "per_page": 20, "category": NotificationCategory.PAYMENTS},
            **_make_jwt(user),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["page"]["number"] == 1
        assert body["data"]["per_page"] == 20
        assert [item["id"] for item in body["data"]["page"]["object_list"]] == [mobile.id]

        unfiltered = api_client.get(self.list_url, {"page": 1}, **_make_jwt(user)).json()
        assert {item["id"] for item in unfiltered["data"]["page"]["object_list"]} == {mobile.id, both.id}

    def test_unread_and_read_actions_exclude_erp_only_notifications(self, api_client):
        user = TenantFactory()
        mobile = NotificationFactory(recipient=user, audience=NotificationAudience.MOBILE, is_read=False)
        erp = NotificationFactory(recipient=user, audience=NotificationAudience.ERP, is_read=False)

        unread = api_client.get(f"{self.list_url}unread-count/", **_make_jwt(user))
        assert unread.json()["data"] == {"unread_count": 1}

        rejected = api_client.post(f"{self.list_url}{erp.id}/read/", **_make_jwt(user))
        assert rejected.status_code == 404

        marked = api_client.post(f"{self.list_url}{mobile.id}/read/", **_make_jwt(user))
        assert marked.status_code == 200
        assert marked.json()["data"]["category"] == NotificationCategory.GENERAL
        mobile.refresh_from_db()
        assert mobile.is_read is True

        read_all = api_client.post(f"{self.list_url}read-all/", **_make_jwt(user))
        assert read_all.status_code == 200
        assert read_all.json()["data"] == {"updated": 0}


@pytest.mark.django_db
class TestMobileDeviceAPI:
    register_url = "/api/v1/mobile/devices/"

    def test_register_upserts_token_and_reassigns_it_to_current_user(self, api_client):
        first_user = TenantFactory()
        second_user = TenantFactory()
        token = "fcm-token"
        DeviceTokenFactory(user=first_user, token=token)

        response = _post(
            api_client,
            self.register_url,
            {
                "token": token,
                "platform": "ios",
                "device_id": "device-1",
                "app_version": "1.2.3+4",
                "locale": "uz",
            },
            **_make_jwt(second_user),
        )

        assert response.status_code == 201
        device = DeviceToken.objects.get(token=token)
        assert device.user_id == second_user.id
        assert device.platform == "ios"
        assert response.json()["data"]["id"] == device.id
        assert response.json()["data"]["is_active"] is True

    def test_unregister_only_deletes_the_current_users_token(self, api_client):
        user = TenantFactory()
        other = TenantFactory()
        device = DeviceTokenFactory(user=user, token="user-token")

        other_response = _post(
            api_client,
            f"{self.register_url}unregister/",
            {"token": device.token},
            **_make_jwt(other),
        )
        assert other_response.status_code == 201
        assert other_response.json()["data"] == {"deleted": 0}
        assert DeviceToken.objects.filter(pk=device.pk).exists()

        own_response = _post(
            api_client,
            f"{self.register_url}unregister/",
            {"token": device.token},
            **_make_jwt(user),
        )
        assert own_response.status_code == 201
        assert own_response.json()["data"] == {"deleted": 1}
        assert not DeviceToken.global_objects.filter(pk=device.pk).exists()


@pytest.mark.django_db
class TestMobileNotificationSettingsAPI:
    url = "/api/v1/mobile/notification-settings/"

    def test_get_creates_defaults_and_master_disable_deletes_tokens(self, api_client):
        user = TenantFactory()
        DeviceTokenFactory(user=user)

        initial = api_client.get(self.url, **_make_jwt(user))
        assert initial.status_code == 200
        assert initial.json()["data"] == {
            "push_enabled": True,
            "payments_enabled": True,
            "bookings_enabled": True,
            "maintenance_enabled": True,
            "leases_enabled": True,
            "messages_enabled": True,
            "general_enabled": True,
        }

        response = _patch(
            api_client,
            self.url,
            {"push_enabled": False, "payments_enabled": False},
            **_make_jwt(user),
        )
        assert response.status_code == 200
        assert response.json()["data"]["push_enabled"] is False
        assert response.json()["data"]["payments_enabled"] is False
        assert not DeviceToken.objects.filter(user=user).exists()

    def test_messages_preference_can_be_updated_and_round_trips(self, api_client):
        user = TenantFactory()

        response = _patch(api_client, self.url, {"messages_enabled": False}, **_make_jwt(user))

        assert response.status_code == 200
        assert response.json()["data"]["messages_enabled"] is False
        preference = NotificationPreference.objects.get(user=user)
        assert preference.messages_enabled is False

        round_trip = api_client.get(self.url, **_make_jwt(user))

        assert round_trip.status_code == 200
        assert round_trip.json()["data"]["messages_enabled"] is False

    def test_messages_preference_gates_chat_notifications(self):
        user = TenantFactory()
        preference = NotificationPreference.objects.create(user=user)

        assert preference.messages_enabled is True
        assert preference.allows_category(NotificationCategory.MESSAGES) is True

        preference.messages_enabled = False
        preference.save(update_fields=["messages_enabled", "updated_at"])
        assert preference.allows_category(NotificationCategory.MESSAGES) is False

        preference.push_enabled = False
        preference.save(update_fields=["push_enabled", "updated_at"])
        assert preference.allows_category(NotificationCategory.MESSAGES) is False
