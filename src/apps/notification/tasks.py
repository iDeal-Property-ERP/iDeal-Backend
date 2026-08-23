"""Background tasks for notification delivery."""

from notification.models import Notification
from notification.services.push import PushService

from core.constants import NotificationCategory, NotificationType


def send_push_for_notification(notification_id: int) -> int:
    """django-q2 task: deliver one notification to the recipient's devices."""
    try:
        notification = Notification.objects.select_related("recipient").get(pk=notification_id)
    except Notification.DoesNotExist:
        return 0

    return PushService().send_for_notification(notification)


def send_chat_message_push(conversation_id: int) -> int:
    """Deliver a privacy-safe first-unread alert for a mobile conversation."""
    from chat.models import Conversation
    from django.utils.translation import override

    try:
        conversation = Conversation.objects.select_related("user", "listing__property").get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return 0

    if conversation.user_unread_count == 0 or conversation.user_muted or conversation.user_deleted_at is not None:
        return 0

    replacement_key = f"chat_conversation:{conversation.id}"
    listing_title = conversation.listing.property.name

    def build_message(device):
        language = (device.locale or "en").replace("_", "-").split("-", 1)[0]
        with override(language):
            from django.utils.translation import gettext as _
            from notification.services.providers.base import PushMessage

            return PushMessage(
                token=device.token,
                title=str(_("New message")),
                body=str(_("You have a new message about %(listing)s.")) % {"listing": listing_title},
                data={
                    "type": NotificationType.CHAT_MESSAGE,
                    "category": NotificationCategory.MESSAGES,
                    "related_object_type": "chat_conversation",
                    "related_object_id": str(conversation.id),
                    "replacement_key": replacement_key,
                    "deep_link": f"ideal://chats/{conversation.id}",
                },
                replacement_key=replacement_key,
            )

    return PushService().send_to_user(
        recipient=conversation.user,
        category=NotificationCategory.MESSAGES,
        message_factory=build_message,
    )
