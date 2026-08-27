"""Notification dispatch — the single choke point for in-app notifications."""

import logging

import django_q.tasks
from notification.models import DeviceToken, Notification
from notification.services.push import PushService

from core.constants import NotificationAudience, NotificationCategory

logger = logging.getLogger(__name__)


def notify(
    *,
    recipient,
    type,
    title,
    body=None,
    related_object_type=None,
    related_object_id=None,
    audience: str = NotificationAudience.BOTH,
    translations: dict | None = None,
):
    """Create an in-app notification for ``recipient`` and dispatch mobile push when applicable."""
    title_str = str(title)
    body_str = str(body) if body is not None else None
    notification = Notification(
        recipient=recipient,
        type=type,
        audience=audience,
        title=title_str,
        title_en=title_str,
        title_uz=title_str,
        title_ru=title_str,
        body=body_str,
        body_en=body_str,
        body_uz=body_str,
        body_ru=body_str,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
    )
    if translations:
        from core.services.localization import LocalizedContentService

        LocalizedContentService().apply_translations(notification, translations, ["title", "body"])
    notification.save()

    if audience in (NotificationAudience.MOBILE, NotificationAudience.BOTH) and _should_enqueue_mobile_push(
        notification
    ):
        try:
            django_q.tasks.async_task("notification.tasks.send_push_for_notification", notification.id)
        except Exception:
            logger.warning("Unable to enqueue push notification id=%s", notification.id, exc_info=True)

    return notification


def _should_enqueue_mobile_push(notification: Notification) -> bool:
    """Avoid queueing a delivery task when there is no eligible mobile target."""
    return _has_eligible_mobile_target(recipient=notification.recipient, category=notification.category)


def enqueue_chat_message_push(*, recipient, conversation_id: int) -> None:
    """Queue the first push for an unread mobile chat burst."""
    if not _has_eligible_mobile_target(recipient=recipient, category=NotificationCategory.MESSAGES):
        return

    try:
        django_q.tasks.async_task("notification.tasks.send_chat_message_push", conversation_id)
    except Exception:
        logger.warning("Unable to enqueue chat push conversation_id=%s", conversation_id, exc_info=True)


def _has_eligible_mobile_target(*, recipient, category: str) -> bool:
    if not DeviceToken.objects.filter(user_id=recipient.id, is_active=True).exists():
        return False

    return PushService().should_send_to_user(user=recipient, category=category)
