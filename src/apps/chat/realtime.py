"""Durable, audience-scoped chat realtime events."""

from __future__ import annotations

from dataclasses import dataclass

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from chat.models import ChatRealtimeEvent, Conversation, Message
from django.db import transaction
from django.utils import timezone

from core.constants import ChatMessageKind

USER_AUDIENCE = "user"
STAFF_AUDIENCE = "staff"


@dataclass(frozen=True)
class RealtimeEventSpec:
    audience: str
    event_type: str


def user_group(user_id: int) -> str:
    return f"chat.user.{user_id}"


def staff_group() -> str:
    return "chat.staff"


def message_payload(message: Message) -> dict:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "sender_side": message.sender_side,
        "sender_name": " ".join(part for part in (message.sender.first_name, message.sender.last_name) if part),
        "kind": message.kind,
        "text": message.text,
        "image_url": message.image.url if message.image else None,
        "image_width": message.image_width,
        "image_height": message.image_height,
        "image_size_bytes": message.image_size_bytes,
        "client_id": message.client_id,
        "read_at": message.read_at.isoformat() if message.read_at else None,
        "is_read": message.read_at is not None,
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat(),
    }


def conversation_payload(conversation: Conversation) -> dict:
    last_message = conversation.last_message
    if last_message is None:
        preview = None
    elif last_message.kind == ChatMessageKind.IMAGE:
        preview = "Photo"
    else:
        preview = (last_message.text or "")[:120]
    return {
        "id": conversation.id,
        "user_deleted_at": conversation.user_deleted_at.isoformat() if conversation.user_deleted_at else None,
        "user_muted": conversation.user_muted,
        "user_archived_at": conversation.user_archived_at.isoformat() if conversation.user_archived_at else None,
        "staff_archived_at": conversation.staff_archived_at.isoformat() if conversation.staff_archived_at else None,
        "is_user_blocked": conversation.is_user_blocked,
        "user_last_read_message_id": conversation.user_last_read_message_id,
        "staff_last_read_message_id": conversation.staff_last_read_message_id,
        "user_unread_count": conversation.user_unread_count,
        "staff_unread_count": conversation.staff_unread_count,
        "last_message_id": conversation.last_message_id,
        "last_message_at": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
        "last_message_preview": preview,
        "updated_at": conversation.updated_at.isoformat(),
    }


def queue_events(
    conversation: Conversation,
    *,
    specs: tuple[RealtimeEventSpec, ...],
    message: Message | None = None,
) -> None:
    """Persist events inside the caller's transaction and publish after commit."""
    if not specs:
        return

    update_fields: list[str] = []
    versions: dict[str, int] = {}
    for audience in {spec.audience for spec in specs}:
        field_name = "user_realtime_version" if audience == USER_AUDIENCE else "staff_realtime_version"
        setattr(conversation, field_name, getattr(conversation, field_name) + 1)
        update_fields.append(field_name)
        versions[audience] = getattr(conversation, field_name)
    conversation.save(update_fields=[*update_fields, "updated_at"])

    base_payload = {"conversation": conversation_payload(conversation)}
    if message is not None:
        base_payload["message"] = message_payload(message)

    rows = [
        ChatRealtimeEvent(
            audience=spec.audience,
            recipient_user_id=conversation.user_id if spec.audience == USER_AUDIENCE else None,
            conversation_id=conversation.id,
            conversation_version=versions[spec.audience],
            event_type=spec.event_type,
            payload=base_payload,
        )
        for spec in specs
    ]
    created = ChatRealtimeEvent.objects.bulk_create(rows)
    event_ids = tuple(event.id for event in created)
    transaction.on_commit(lambda: publish_events(event_ids))


def publish_events(event_ids: tuple[int, ...]) -> None:
    """Fan out committed outbox rows; replay covers a transient Redis failure."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    for event in ChatRealtimeEvent.objects.filter(id__in=event_ids).order_by("id"):
        group = user_group(event.recipient_user_id) if event.audience == USER_AUDIENCE else staff_group()
        async_to_sync(channel_layer.group_send)(
            group,
            {
                "type": "chat.realtime",
                "event": serialize_event(event),
            },
        )


def serialize_event(event: ChatRealtimeEvent) -> dict:
    return {
        "type": event.event_type,
        "event_id": event.id,
        "conversation_id": event.conversation_id,
        "conversation_version": event.conversation_version,
        "occurred_at": event.created_at.isoformat(),
        "data": event.payload,
    }


def prune_expired_events() -> int:
    from datetime import timedelta

    from django.conf import settings

    threshold = timezone.now() - timedelta(days=settings.CHAT_REALTIME_EVENT_RETENTION_DAYS)
    deleted, _ = ChatRealtimeEvent.objects.filter(created_at__lt=threshold).delete()
    return deleted


def specs_for_both(event_type: str) -> tuple[RealtimeEventSpec, ...]:
    return (
        RealtimeEventSpec(USER_AUDIENCE, event_type),
        RealtimeEventSpec(STAFF_AUDIENCE, event_type),
    )
