import logging

from django.conf import settings
from notification.models import DeviceToken, NotificationPreference

from .providers.base import PushDeliveryError, PushMessage, PushProvider, PushTokenInvalidError
from .providers.fcm import FCMPushProvider

logger = logging.getLogger(__name__)


class PushService:
    """Apply push preferences and deliver a notification to active device tokens."""

    def __init__(self, provider: PushProvider | None = None):
        self._provider = provider

    @property
    def provider(self) -> PushProvider:
        if self._provider is None:
            self._provider = FCMPushProvider()
        return self._provider

    def should_send(self, notification) -> bool:
        if not settings.FCM_ENABLED:
            return False

        preference, _ = NotificationPreference.objects.get_or_create(user=notification.recipient)
        return preference.allows_category(notification.category)

    def send_for_notification(self, notification) -> int:
        try:
            if not self.should_send(notification):
                return 0
            devices = DeviceToken.objects.filter(user_id=notification.recipient_id, is_active=True)
        except Exception:
            logger.warning("Unable to prepare push delivery notification id=%s", notification.id, exc_info=True)
            return 0

        data = {
            "notification_id": str(notification.id),
            "type": str(notification.type),
            "category": str(notification.category),
            "related_object_type": ""
            if notification.related_object_type is None
            else str(notification.related_object_type),
            "related_object_id": "" if notification.related_object_id is None else str(notification.related_object_id),
            "deep_link": f"ideal://notifications/{notification.id}",
        }
        delivered = 0

        for device in devices:
            message = PushMessage(
                token=device.token,
                title=str(notification.title),
                body="" if notification.body is None else str(notification.body),
                data=data,
            )
            try:
                self.provider.send(message)
            except PushTokenInvalidError:
                try:
                    device.hard_delete()
                except Exception:
                    logger.warning("Unable to prune invalid push token device_id=%s", device.id, exc_info=True)
                continue
            except PushDeliveryError:
                logger.warning("Push delivery failed device_id=%s notification_id=%s", device.id, notification.id)
                continue
            except Exception:
                logger.warning(
                    "Unexpected push delivery failure device_id=%s notification_id=%s", device.id, notification.id
                )
                continue
            delivered += 1

        return delivered
