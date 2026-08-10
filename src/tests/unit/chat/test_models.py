import pytest
from chat.models import Conversation, ConversationReport, Message
from django.db import IntegrityError, transaction

from core.constants import ChatMessageKind, ChatSenderSide
from tests.factories import ConversationFactory, MessageFactory


@pytest.mark.django_db
def test_chat_models_use_fixed_table_names():
    assert Conversation._meta.db_table == "chat_conversations"
    assert Message._meta.db_table == "chat_messages"
    assert ConversationReport._meta.db_table == "chat_conversation_reports"


@pytest.mark.django_db
def test_active_conversation_is_unique_but_soft_deleted_row_allows_reopen():
    conversation = ConversationFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        Conversation.objects.create(listing=conversation.listing, user=conversation.user)

    conversation.delete()
    reopened = Conversation.objects.create(listing=conversation.listing, user=conversation.user)

    assert reopened.pk != conversation.pk
    assert Conversation.objects.filter(listing=conversation.listing, user=conversation.user).count() == 1


@pytest.mark.django_db
def test_message_client_id_is_unique_but_null_ids_are_repeatable():
    conversation = ConversationFactory()
    MessageFactory(conversation=conversation, client_id="retry-key")

    with pytest.raises(IntegrityError), transaction.atomic():
        Message.objects.create(
            conversation=conversation,
            sender=conversation.user,
            sender_side=ChatSenderSide.USER,
            kind=ChatMessageKind.TEXT,
            text="duplicate",
            client_id="retry-key",
        )

    MessageFactory(conversation=conversation, client_id=None)
    MessageFactory(conversation=conversation, client_id=None)
    assert Message.objects.filter(conversation=conversation).count() == 3


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "text"),
    [
        (ChatMessageKind.TEXT, None),
        (ChatMessageKind.IMAGE, None),
    ],
)
def test_message_payload_constraint_requires_kind_specific_payload(kind, text):
    conversation = ConversationFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        Message.objects.create(
            conversation=conversation,
            sender=conversation.user,
            sender_side=ChatSenderSide.USER,
            kind=kind,
            text=text,
        )


def test_message_ordering_is_the_monotonic_id_cursor():
    assert Message._meta.ordering == ["id"]
