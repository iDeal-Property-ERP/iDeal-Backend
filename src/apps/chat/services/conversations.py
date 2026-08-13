from account.models import User
from chat.exceptions import ChatReadOnlyError, ChatUnavailableError
from chat.models import Conversation, ConversationReport, Message
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from notification.services import notify

from core.constants import (
    ChatMessageKind,
    ChatSenderSide,
    ListingStatus,
    NotificationAudience,
    NotificationType,
    UserRole,
)


def _conversation_queryset():
    return Conversation.objects.select_related("listing__property__district", "user", "last_message").prefetch_related(
        "listing__property__photos"
    )


def visible_for_user(user):
    """Return conversations belonging to ``user`` that the user has not deleted."""
    return _conversation_queryset().filter(user=user, user_deleted_at__isnull=True)


def visible_for_staff():
    """Return all conversations that management has not purged."""
    return _conversation_queryset()


def get_for_user_or_404(conversation_id, user):
    try:
        return visible_for_user(user).get(pk=conversation_id)
    except Conversation.DoesNotExist as exc:
        raise Http404 from exc


def get_for_staff_or_404(conversation_id):
    try:
        return visible_for_staff().get(pk=conversation_id)
    except Conversation.DoesNotExist as exc:
        raise Http404 from exc


def open_or_get(listing, user):
    """Open the user's idempotent conversation for a published listing."""
    if listing.status != ListingStatus.PUBLISHED or getattr(listing, "deleted_at", None) is not None:
        raise ChatUnavailableError(str(_("Chat is unavailable for this listing.")))

    try:
        with transaction.atomic():
            return Conversation.objects.get_or_create(listing=listing, user=user)
    except IntegrityError:
        conversation = Conversation.objects.get(listing=listing, user=user)
        return conversation, False


def _lock_conversation(conversation):
    locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
    for relation in ("listing", "user", "last_message"):
        if relation in conversation._state.fields_cache:
            setattr(locked, relation, getattr(conversation, relation))
    return locked


def _sync_conversation_state(source, target):
    for field_name in (
        "user_deleted_at",
        "user_muted",
        "user_last_read_message_id",
        "user_unread_count",
        "staff_last_read_message_id",
        "staff_unread_count",
        "user_archived_at",
        "staff_archived_at",
        "is_user_blocked",
        "blocked_at",
        "last_message_at",
        "updated_at",
    ):
        setattr(target, field_name, getattr(source, field_name))
    target.blocked_by_id = source.blocked_by_id
    target.last_message_id = source.last_message_id
    for relation in ("blocked_by", "last_message"):
        if relation in source._state.fields_cache:
            setattr(target, relation, getattr(source, relation))


def _validate_side(side):
    if side not in (ChatSenderSide.USER, ChatSenderSide.STAFF):
        raise ValueError(str(_("Invalid chat sender side.")))


def assert_user_can_write(conversation):
    """Raise when management has blocked the mobile user from replying."""
    if conversation.is_user_blocked:
        raise ChatReadOnlyError(str(_("This conversation is read-only.")))


def assert_staff_can_write(conversation):
    """Raise when the mobile user has deleted the conversation."""
    if conversation.user_deleted_at is not None:
        raise ChatReadOnlyError(str(_("This conversation was deleted by the user.")))


def send_message(conversation, *, sender, side, text=None, image=None, client_id=None):
    """Create an idempotent message and update the conversation inbox state."""
    _validate_side(side)
    if side == ChatSenderSide.USER:
        assert_user_can_write(conversation)
    else:
        assert_staff_can_write(conversation)

    with transaction.atomic():
        locked = _lock_conversation(conversation)
        if side == ChatSenderSide.USER:
            assert_user_can_write(locked)
        else:
            assert_staff_can_write(locked)

        kind = ChatMessageKind.IMAGE if image is not None else ChatMessageKind.TEXT
        defaults = {
            "sender": sender,
            "sender_side": side,
            "kind": kind,
            "text": text,
            "image": image,
            "image_size_bytes": getattr(image, "size", None) if image is not None else None,
        }
        if client_id is None:
            message = Message.objects.create(conversation=locked, **defaults)
            created = True
        else:
            message, created = Message.objects.get_or_create(
                conversation=locked,
                client_id=client_id,
                defaults=defaults,
            )

        if not created:
            return message, False

        locked.last_message = message
        locked.last_message_at = message.created_at
        unread_field = "staff_unread_count" if side == ChatSenderSide.USER else "user_unread_count"
        setattr(locked, unread_field, getattr(locked, unread_field) + 1)
        locked.save(update_fields=["last_message", "last_message_at", unread_field, "updated_at"])
        _sync_conversation_state(locked, conversation)

        if side == ChatSenderSide.STAFF and not locked.user_muted:
            preview = str(_("Photo")) if kind == ChatMessageKind.IMAGE else (text or "")[:120]
            transaction.on_commit(
                lambda recipient=locked.user, conversation_id=locked.id, body=preview: notify(
                    recipient=recipient,
                    type=NotificationType.CHAT_MESSAGE,
                    title=str(_("New message")),
                    body=body,
                    related_object_type="chat_conversation",
                    related_object_id=conversation_id,
                    audience=NotificationAudience.MOBILE,
                )
            )

    return message, True


def mark_read(conversation, *, side, up_to_message_id=None):
    """Advance one side's read watermark and mark the peer's messages read."""
    _validate_side(side)
    with transaction.atomic():
        locked = _lock_conversation(conversation)
        if side == ChatSenderSide.USER:
            watermark_field = "user_last_read_message_id"
            unread_field = "user_unread_count"
        else:
            watermark_field = "staff_last_read_message_id"
            unread_field = "staff_unread_count"

        current_watermark = getattr(locked, watermark_field)
        candidate = up_to_message_id
        if candidate is None:
            candidate = Message.objects.filter(conversation=locked).order_by("-id").values_list("id", flat=True).first()
        watermark = current_watermark
        if candidate is not None and (watermark is None or candidate > watermark):
            watermark = candidate

        if watermark is not None:
            peer_side = ChatSenderSide.STAFF if side == ChatSenderSide.USER else ChatSenderSide.USER
            Message.objects.filter(
                conversation=locked,
                sender_side=peer_side,
                id__lte=watermark,
                read_at__isnull=True,
            ).update(read_at=timezone.now())

        previous_unread_count = getattr(locked, unread_field)
        setattr(locked, watermark_field, watermark)
        setattr(locked, unread_field, 0)
        if watermark != current_watermark or previous_unread_count != 0:
            locked.save(update_fields=[watermark_field, unread_field, "updated_at"])
        _sync_conversation_state(locked, conversation)

    return conversation


def set_archived(conversation, *, side, value: bool):
    _validate_side(side)
    with transaction.atomic():
        locked = _lock_conversation(conversation)
        field_name = "user_archived_at" if side == ChatSenderSide.USER else "staff_archived_at"
        setattr(locked, field_name, timezone.now() if value else None)
        locked.save(update_fields=[field_name, "updated_at"])
        _sync_conversation_state(locked, conversation)
    return conversation


def set_muted(conversation, value: bool):
    with transaction.atomic():
        locked = _lock_conversation(conversation)
        locked.user_muted = value
        locked.save(update_fields=["user_muted", "updated_at"])
        _sync_conversation_state(locked, conversation)
    return conversation


def set_blocked(conversation, *, staff_user, value: bool):
    with transaction.atomic():
        locked = _lock_conversation(conversation)
        locked.is_user_blocked = value
        locked.blocked_by = staff_user if value else None
        locked.blocked_at = timezone.now() if value else None
        locked.save(update_fields=["is_user_blocked", "blocked_by", "blocked_at", "updated_at"])
        _sync_conversation_state(locked, conversation)
    return conversation


def delete_for_user(conversation, user):
    """Hide a conversation from its mobile user without removing its row."""
    if conversation.user_id != user.pk:
        raise Http404

    with transaction.atomic():
        locked = _lock_conversation(conversation)
        locked.user_deleted_at = locked.user_deleted_at or timezone.now()
        locked.user_unread_count = 0
        locked.save(update_fields=["user_deleted_at", "user_unread_count", "updated_at"])
        _sync_conversation_state(locked, conversation)
    return conversation


def purge(conversation):
    """Soft-delete a conversation and reclaim every uploaded message image."""
    listing = conversation.listing
    with transaction.atomic():
        locked = _lock_conversation(conversation)
        locked.listing = listing
        messages = list(Message.global_objects.select_for_update().filter(conversation_id=locked.pk))
        for message in messages:
            message.image.delete(save=False)
        locked.delete()
    return locked


def report(conversation, *, reported_by, reason, note=""):
    """Create a report and notify the active management inbox users."""
    with transaction.atomic():
        conversation_report = ConversationReport.objects.create(
            conversation=conversation,
            reported_by=reported_by,
            reason=reason,
            note=note,
        )
        management_users = User.objects.filter(role=UserRole.MANAGEMENT, is_active=True)
        # Management is a small-N shared inbox, so a direct per-user fan-out is sufficient.
        for recipient in management_users:
            transaction.on_commit(
                lambda recipient=recipient, conversation_id=conversation.id: notify(
                    recipient=recipient,
                    type=NotificationType.CHAT_MESSAGE,
                    title=str(_("Conversation reported")),
                    body=note or str(_("A conversation was reported.")),
                    related_object_type="chat_conversation",
                    related_object_id=conversation_id,
                    audience=NotificationAudience.ERP,
                )
            )
    return conversation_report
