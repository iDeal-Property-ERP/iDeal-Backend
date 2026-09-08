import html
import logging

import requests
from django.conf import settings

from core.models import SupportInquiry

logger = logging.getLogger(__name__)


def send_support_inquiry_telegram_alert(inquiry_id: int) -> bool:
    """Send an instant Telegram alert to the administrative channel for a new support inquiry."""
    bot_token = getattr(settings, "LOGGING_TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(settings, "LOGGING_TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return False

    inquiry = SupportInquiry.objects.filter(pk=inquiry_id).first()
    if inquiry is None:
        logger.warning("Support inquiry id=%s does not exist", inquiry_id)
        return False

    created_str = inquiry.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    safe_name = html.escape(inquiry.name)
    safe_email = html.escape(inquiry.email)
    safe_ip = html.escape(inquiry.ip_address or "Unknown")
    safe_msg = html.escape(inquiry.message[:3500])

    text = (
        f"📩 <b>New Support Inquiry (#{inquiry.id})</b>\n\n"
        f"<b>Name:</b> {safe_name}\n"
        f"<b>Email:</b> {safe_email}\n"
        f"<b>Created:</b> {created_str}\n"
        f"<b>IP:</b> {safe_ip}\n\n"
        f"<b>Message:</b>\n{safe_msg}"
    )

    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        response = requests.post(
            api_url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=5,
        )
        if not response.ok:
            logger.warning("Telegram sendMessage returned %s: %s", response.status_code, response.text)
            return False
        return True
    except Exception as exc:
        logger.warning("Failed to send support inquiry telegram alert: %s", exc)
        return False
