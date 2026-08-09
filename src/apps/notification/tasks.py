"""Background tasks for notification delivery."""

from notification.models import Notification
from notification.services.push import PushService


def send_push_for_notification(notification_id: int) -> int:
    """django-q2 task: deliver one notification to the recipient's devices."""
    try:
        notification = Notification.objects.select_related("recipient").get(pk=notification_id)
    except Notification.DoesNotExist:
        return 0

    return PushService().send_for_notification(notification)
