import logging
from collections.abc import Callable

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
        return self.should_send_to_user(user=notification.recipient, category=notification.category)

    def should_send_to_user(self, *, user, category: str) -> bool:
        if not settings.FCM_ENABLED:
            return False

        preference, _ = NotificationPreference.objects.get_or_create(user=user)
        return preference.allows_category(category)

    def send_for_notification(self, notification) -> int:
        def _build_push_message(_device):
            loc = getattr(_device, "locale", "en") or "en"
            title = getattr(notification, f"title_{loc}", None) or str(notification.title)
            body_val = getattr(notification, f"body_{loc}", None) or notification.body
            return PushMessage(
                token=_device.token,
                title=title,
                body="" if body_val is None else str(body_val),
                data={
                    "notification_id": str(notification.id),
                    "type": str(notification.type),
                    "category": str(notification.category),
                    "related_object_type": ""
                    if notification.related_object_type is None
                    else str(notification.related_object_type),
                    "related_object_id": ""
                    if notification.related_object_id is None
                    else str(notification.related_object_id),
                    "deep_link": f"ideal://notifications/{notification.id}",
                },
            )

        return self.send_to_user(
            recipient=notification.recipient,
            category=notification.category,
            message_factory=_build_push_message,
        )

    def send_to_user(
        self,
        *,
        recipient,
        category: str,
        message_factory: Callable[[DeviceToken], PushMessage],
    ) -> int:
        try:
            if not self.should_send_to_user(user=recipient, category=category):
                return 0
            devices = DeviceToken.objects.filter(user_id=recipient.id, is_active=True)
        except Exception:
            logger.warning("Unable to prepare push delivery recipient_id=%s", recipient.id, exc_info=True)
            return 0
        delivered = 0

        for device in devices:
            message = message_factory(device)
            try:
                self.provider.send(message)
            except PushTokenInvalidError:
                try:
                    device.hard_delete()
                except Exception:
                    logger.warning("Unable to prune invalid push token device_id=%s", device.id, exc_info=True)
                continue
            except PushDeliveryError:
                logger.warning("Push delivery failed device_id=%s", device.id)
                continue
            except Exception:
                logger.warning("Unexpected push delivery failure device_id=%s", device.id)
                continue
            delivered += 1

        return delivered
