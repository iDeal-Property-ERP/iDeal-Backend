"""Background tasks for core services."""

from core.services.support import send_support_inquiry_telegram_alert


def send_support_inquiry_telegram_alert_task(inquiry_id: int) -> bool:
    """django-q2 task: deliver Telegram notification for a new support inquiry."""
    return send_support_inquiry_telegram_alert(inquiry_id)
