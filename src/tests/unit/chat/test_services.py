from base64 import b64decode
from unittest.mock import patch

import pytest
from chat.exceptions import ChatReadOnlyError, ChatUnavailableError
from chat.models import Conversation, Message
from chat.services import (
    assert_staff_can_write,
    assert_user_can_write,
    delete_for_user,
    mark_read,
    open_or_get,
    purge,
    report,
    send_message,
    set_blocked,
    visible_for_staff,
    visible_for_user,
)
from django.core.files.uploadedfile import SimpleUploadedFile
from marketplace.models import Listing

from core.constants import (
    ChatMessageKind,
    ChatReportReason,
    ChatSenderSide,
    ListingStatus,
    NotificationAudience,
)
from tests.factories import ConversationFactory, ListingFactory, TenantFactory, UserFactory

ONE_PIXEL_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.mark.django_db
def test_open_or_get_is_idempotent_and_requires_published_listing():
    listing = ListingFactory()
    user = TenantFactory()

    # A Property post_save signal auto-creates a PUBLISHED listing, and
    # ListingFactory uses django_get_or_create=("property",), so a `status`
    # kwarg on the factory is silently discarded. Force the state explicitly.
    listing.status = ListingStatus.DRAFT
    listing.save(update_fields=["status", "updated_at"])

    with pytest.raises(ChatUnavailableError):
        open_or_get(listing, user)

    listing.status = ListingStatus.PUBLISHED
    listing.save(update_fields=["status", "updated_at"])
    first, first_created = open_or_get(listing, user)
    second, second_created = open_or_get(listing, user)

    assert first_created is True
    assert second_created is False
    assert second.pk == first.pk


@pytest.mark.django_db
def test_send_message_reuses_existing_client_id_without_a_second_row():
    conversation = ConversationFactory()

    first, first_created = send_message(
        conversation,
        sender=conversation.user,
        side=ChatSenderSide.USER,
        text="hello",
        client_id="optimistic-1",
    )
    second, second_created = send_message(
        conversation,
        sender=conversation.user,
        side=ChatSenderSide.USER,
        text="retry should not replace this",
        client_id="optimistic-1",
    )

    assert first_created is True
    assert second_created is False
    assert second.pk == first.pk
    assert Message.objects.filter(conversation=conversation).count() == 1


@pytest.mark.django_db
def test_send_message_increments_only_the_other_side_unread_count():
    conversation = ConversationFactory()
    staff = UserFactory()

    send_message(conversation, sender=conversation.user, side=ChatSenderSide.USER, text="question")
    conversation.refresh_from_db()
    assert conversation.staff_unread_count == 1
    assert conversation.user_unread_count == 0

    with patch("chat.services.conversations.notify"):
        send_message(conversation, sender=staff, side=ChatSenderSide.STAFF, text="answer")

    conversation.refresh_from_db()
    assert conversation.staff_unread_count == 1
    assert conversation.user_unread_count == 1


@pytest.mark.django_db
def test_staff_reply_notifies_mobile_user_after_commit_with_preview(django_capture_on_commit_callbacks):
    conversation = ConversationFactory()
    staff = UserFactory()

    # The notification is deliberately deferred with transaction.on_commit, and
    # pytest-django's test transaction never commits, so the callbacks have to
    # be drained explicitly.
    with patch("chat.services.conversations.notify") as notify, django_capture_on_commit_callbacks(execute=True):
        send_message(
            conversation,
            sender=staff,
            side=ChatSenderSide.STAFF,
            text="A" * 200,
        )

    notify.assert_called_once()
    kwargs = notify.call_args.kwargs
    assert kwargs["recipient"] == conversation.user
    assert kwargs["audience"] == NotificationAudience.MOBILE
    assert kwargs["body"] == "A" * 120


@pytest.mark.django_db
def test_mark_read_advances_watermark_stamps_peer_messages_and_never_rewinds():
    conversation = ConversationFactory()
    staff = UserFactory()

    user_message, _ = send_message(
        conversation,
        sender=conversation.user,
        side=ChatSenderSide.USER,
        text="question",
    )
    with patch("chat.services.conversations.notify"):
        staff_message, _ = send_message(
            conversation,
            sender=staff,
            side=ChatSenderSide.STAFF,
            text="answer",
        )

    mark_read(conversation, side=ChatSenderSide.USER, up_to_message_id=staff_message.id)
    conversation.refresh_from_db()
    staff_message.refresh_from_db()
    user_message.refresh_from_db()
    first_read_at = staff_message.read_at

    assert conversation.user_last_read_message_id == staff_message.id
    assert conversation.user_unread_count == 0
    assert first_read_at is not None
    assert user_message.read_at is None

    mark_read(conversation, side=ChatSenderSide.USER, up_to_message_id=user_message.id)
    conversation.refresh_from_db()
    staff_message.refresh_from_db()
    assert conversation.user_last_read_message_id == staff_message.id
    assert staff_message.read_at == first_read_at

    mark_read(conversation, side=ChatSenderSide.STAFF, up_to_message_id=staff_message.id)
    conversation.refresh_from_db()
    user_message.refresh_from_db()
    assert conversation.staff_last_read_message_id == staff_message.id
    assert conversation.staff_unread_count == 0
    assert user_message.read_at is not None


@pytest.mark.django_db
def test_delete_for_user_hides_only_the_mobile_view():
    conversation = ConversationFactory()
    user = conversation.user

    delete_for_user(conversation, user)

    assert not visible_for_user(user).filter(pk=conversation.pk).exists()
    assert visible_for_staff().filter(pk=conversation.pk).exists()
    conversation.refresh_from_db()
    assert conversation.user_deleted_at is not None

    with pytest.raises(ChatReadOnlyError):
        assert_staff_can_write(conversation)


@pytest.mark.django_db
def test_blocked_user_cannot_write():
    conversation = ConversationFactory()
    staff = UserFactory()
    set_blocked(conversation, staff_user=staff, value=True)

    with pytest.raises(ChatReadOnlyError):
        assert_user_can_write(conversation)


@pytest.mark.django_db
def test_purge_hides_conversation_everywhere_and_reclaims_message_images():
    conversation = ConversationFactory()
    image = SimpleUploadedFile("photo.png", ONE_PIXEL_PNG, content_type="image/png")
    message = Message.objects.create(
        conversation=conversation,
        sender=conversation.user,
        sender_side=ChatSenderSide.USER,
        kind=ChatMessageKind.IMAGE,
        image=image,
    )

    # Patch ImageFieldFile, not FieldFile: ImageFieldFile.delete forwards to
    # super().delete(save) positionally, so patching the base class would
    # record delete(False) and hide the keyword.
    with patch("django.db.models.fields.files.ImageFieldFile.delete") as delete_image:
        purge(conversation)

    delete_image.assert_called_once_with(save=False)
    assert not visible_for_user(conversation.user).filter(pk=conversation.pk).exists()
    assert not visible_for_staff().filter(pk=conversation.pk).exists()
    assert Conversation.global_objects.get(pk=conversation.pk).deleted_at is not None
    assert Message.global_objects.get(pk=message.pk).deleted_at is not None


@pytest.mark.django_db
def test_report_notifies_each_active_management_user_in_erp_audience(django_capture_on_commit_callbacks):
    conversation = ConversationFactory()
    first_manager = UserFactory()
    second_manager = UserFactory()

    with patch("chat.services.conversations.notify") as notify, django_capture_on_commit_callbacks(execute=True):
        conversation_report = report(
            conversation,
            reported_by=conversation.user,
            reason=ChatReportReason.SPAM,
            note="suspicious content",
        )

    assert conversation_report.conversation_id == conversation.id
    assert notify.call_count == 2
    assert {call.kwargs["recipient"] for call in notify.call_args_list} == {first_manager, second_manager}
    assert all(call.kwargs["audience"] == NotificationAudience.ERP for call in notify.call_args_list)


@pytest.mark.django_db
def test_visibility_excludes_purged_conversations():
    conversation = ConversationFactory()
    user = conversation.user
    purge(conversation)

    assert not visible_for_user(user).filter(pk=conversation.pk).exists()
    assert not visible_for_staff().filter(pk=conversation.pk).exists()


def test_listing_factory_defaults_to_published_model():
    assert Listing._meta.get_field("status").default == ListingStatus.PUBLISHED
