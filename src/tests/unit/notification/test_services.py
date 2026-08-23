from unittest.mock import patch

import pytest
from django.test import override_settings
from notification.models import Notification
from notification.services import enqueue_chat_message_push, notify

from core.constants import NotificationAudience, NotificationType
from tests.factories import DeviceTokenFactory, NotificationPreferenceFactory, TenantFactory


@pytest.mark.django_db
def test_notify_defaults_to_both_audience_without_push_delivery():
    user = TenantFactory()

    notification = notify(
        recipient=user,
        type=NotificationType.GENERAL,
        title="Hello",
        body="World",
    )

    assert notification.audience == NotificationAudience.BOTH
    assert Notification.objects.filter(pk=notification.pk).exists()


@pytest.mark.django_db
@override_settings(FCM_ENABLED=True)
def test_notify_only_enqueues_mobile_push_for_an_eligible_device():
    user = TenantFactory()

    with patch("notification.services.notifications.django_q.tasks.async_task") as enqueue:
        notify(
            recipient=user,
            type=NotificationType.GENERAL,
            title="No device",
            audience=NotificationAudience.MOBILE,
        )
        enqueue.assert_not_called()

        DeviceTokenFactory(user=user)
        NotificationPreferenceFactory(user=user, push_enabled=False)
        notify(
            recipient=user,
            type=NotificationType.GENERAL,
            title="Disabled",
            audience=NotificationAudience.MOBILE,
        )
        enqueue.assert_not_called()

        preference = user.notification_preference
        preference.push_enabled = True
        preference.save(update_fields=["push_enabled"])
        notification = notify(
            recipient=user,
            type=NotificationType.GENERAL,
            title="Enabled",
            audience=NotificationAudience.MOBILE,
        )

    enqueue.assert_called_once_with("notification.tasks.send_push_for_notification", notification.id)


@pytest.mark.django_db
@override_settings(FCM_ENABLED=True)
def test_chat_push_enqueue_requires_an_eligible_messages_target():
    user = TenantFactory()

    with patch("notification.services.notifications.django_q.tasks.async_task") as enqueue:
        enqueue_chat_message_push(recipient=user, conversation_id=12)
        enqueue.assert_not_called()

        DeviceTokenFactory(user=user)
        NotificationPreferenceFactory(user=user, messages_enabled=False)
        enqueue_chat_message_push(recipient=user, conversation_id=12)
        enqueue.assert_not_called()

        preference = user.notification_preference
        preference.messages_enabled = True
        preference.save(update_fields=["messages_enabled"])
        enqueue_chat_message_push(recipient=user, conversation_id=12)

    enqueue.assert_called_once_with("notification.tasks.send_chat_message_push", 12)
