import pytest
from django.test import override_settings
from notification.models import DeviceToken
from notification.services import PushService
from notification.services.providers.base import PushDeliveryError, PushMessage, PushProvider, PushTokenInvalidError

from tests.factories import DeviceTokenFactory, NotificationFactory


class FakePushProvider(PushProvider):
    def __init__(self, *, invalid_tokens=None, failed_tokens=None):
        self.messages = []
        self.invalid_tokens = set(invalid_tokens or ())
        self.failed_tokens = set(failed_tokens or ())

    def send(self, message: PushMessage) -> None:
        self.messages.append(message)
        if message.token in self.invalid_tokens:
            raise PushTokenInvalidError("invalid token")
        if message.token in self.failed_tokens:
            raise PushDeliveryError("temporary provider failure")


@pytest.mark.django_db
def test_push_service_sends_to_each_active_device_and_builds_payload():
    notification = NotificationFactory(related_object_type="payment", related_object_id=42)
    active_one = DeviceTokenFactory(user=notification.recipient)
    active_two = DeviceTokenFactory(user=notification.recipient)
    DeviceTokenFactory(user=notification.recipient, is_active=False)
    provider = FakePushProvider()

    with override_settings(FCM_ENABLED=True):
        delivered = PushService(provider=provider).send_for_notification(notification)

    assert delivered == 2
    assert {message.token for message in provider.messages} == {active_one.token, active_two.token}
    assert all(message.data["notification_id"] == str(notification.id) for message in provider.messages)
    assert all(message.data["related_object_id"] == "42" for message in provider.messages)
    assert all(message.data["deep_link"] == f"ideal://notifications/{notification.id}" for message in provider.messages)


@pytest.mark.django_db
def test_push_service_prunes_invalid_token_and_continues_delivery():
    notification = NotificationFactory()
    invalid = DeviceTokenFactory(user=notification.recipient)
    valid = DeviceTokenFactory(user=notification.recipient)
    provider = FakePushProvider(invalid_tokens={invalid.token})

    with override_settings(FCM_ENABLED=True):
        delivered = PushService(provider=provider).send_for_notification(notification)

    assert delivered == 1
    assert {message.token for message in provider.messages} == {invalid.token, valid.token}
    assert not DeviceToken.global_objects.filter(pk=invalid.pk).exists()
    assert DeviceToken.objects.filter(pk=valid.pk).exists()


@pytest.mark.django_db
def test_push_service_keeps_token_after_generic_delivery_failure():
    notification = NotificationFactory()
    failed = DeviceTokenFactory(user=notification.recipient)
    valid = DeviceTokenFactory(user=notification.recipient)
    provider = FakePushProvider(failed_tokens={failed.token})

    with override_settings(FCM_ENABLED=True):
        delivered = PushService(provider=provider).send_for_notification(notification)

    assert delivered == 1
    assert DeviceToken.objects.filter(pk=failed.pk).exists()
    assert DeviceToken.objects.filter(pk=valid.pk).exists()


@pytest.mark.django_db
def test_push_service_does_not_send_when_fcm_is_disabled():
    notification = NotificationFactory()
    DeviceTokenFactory(user=notification.recipient)
    provider = FakePushProvider()

    with override_settings(FCM_ENABLED=False):
        assert PushService(provider=provider).should_send(notification) is False
        assert PushService(provider=provider).send_for_notification(notification) == 0

    assert provider.messages == []
