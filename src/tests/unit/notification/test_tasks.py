from types import SimpleNamespace
from unittest.mock import patch

import pytest
from chat.services import mark_read, send_message
from notification.tasks import send_chat_message_push

from core.constants import ChatSenderSide, NotificationCategory, NotificationType
from tests.factories import ConversationFactory, UserFactory


@pytest.mark.django_db
def test_chat_push_task_sends_generic_listing_alert_with_stable_replacement_key():
    conversation = ConversationFactory()
    staff = UserFactory()
    send_message(conversation, sender=staff, side=ChatSenderSide.STAFF, text="private preview")

    with patch("notification.tasks.PushService") as service_class:
        service_class.return_value.send_to_user.return_value = 1
        delivered = send_chat_message_push(conversation.id)

    assert delivered == 1
    kwargs = service_class.return_value.send_to_user.call_args.kwargs
    assert kwargs["recipient"] == conversation.user
    assert kwargs["category"] == NotificationCategory.MESSAGES
    message = kwargs["message_factory"](SimpleNamespace(token="token", locale="en"))
    assert message.title == "New message"
    assert message.body == f"You have a new message about {conversation.listing.property.name}."
    assert "private preview" not in message.body
    assert message.data == {
        "type": NotificationType.CHAT_MESSAGE,
        "category": NotificationCategory.MESSAGES,
        "related_object_type": "chat_conversation",
        "related_object_id": str(conversation.id),
        "replacement_key": f"chat_conversation:{conversation.id}",
        "deep_link": f"ideal://chats/{conversation.id}",
    }
    assert message.replacement_key == f"chat_conversation:{conversation.id}"

    russian_message = kwargs["message_factory"](SimpleNamespace(token="ru-token", locale="ru"))
    assert russian_message.title == "Новое сообщение"
    assert russian_message.body == f"У вас новое сообщение по объявлению {conversation.listing.property.name}."

    uzbek_message = kwargs["message_factory"](SimpleNamespace(token="uz-token", locale="uz"))
    assert uzbek_message.title == "Yangi xabar"
    assert uzbek_message.body == f"{conversation.listing.property.name} e'loni bo'yicha yangi xabaringiz bor."


@pytest.mark.django_db
def test_chat_push_task_drops_an_alert_that_was_read_before_delivery():
    conversation = ConversationFactory()
    staff = UserFactory()
    message, _ = send_message(conversation, sender=staff, side=ChatSenderSide.STAFF, text="answer")
    mark_read(conversation, side=ChatSenderSide.USER, up_to_message_id=message.id)

    with patch("notification.tasks.PushService") as service_class:
        assert send_chat_message_push(conversation.id) == 0

    service_class.assert_not_called()
