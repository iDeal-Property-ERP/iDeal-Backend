"""Authenticated realtime delivery for listing-scoped conversations."""

from __future__ import annotations

from datetime import timedelta

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from chat.models import ChatRealtimeEvent
from chat.realtime import STAFF_AUDIENCE, USER_AUDIENCE, serialize_event, staff_group, user_group
from chat.services import visible_for_staff, visible_for_user
from django.conf import settings
from django.utils import timezone

from core.constants import UserRole


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """One socket per signed-in client with replayable durable chat events."""

    heartbeat_seconds = 25

    async def connect(self):
        user = self.scope["user"]
        token = self.scope.get("chat_jwt")
        if not getattr(user, "is_authenticated", False) or token is None:
            await self.close(code=4401)
            return
        if token.exp <= timezone.now():
            await self.close(code=4401)
            return

        self.user_id = user.id
        self.audience = STAFF_AUDIENCE if user.role == UserRole.MANAGEMENT else USER_AUDIENCE
        self.group_name = staff_group() if self.audience == STAFF_AUDIENCE else user_group(user.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(
            {
                "type": "chat.ready",
                "version": 1,
                "latest_event_id": await self._latest_event_id(),
                "server_time": timezone.now().isoformat(),
                "heartbeat_seconds": self.heartbeat_seconds,
            }
        )

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name is not None:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        message_type = content.get("type") if isinstance(content, dict) else None
        if message_type == "chat.ping":
            await self.send_json(
                {
                    "type": "chat.pong",
                    "latest_event_id": await self._latest_event_id(),
                    "server_time": timezone.now().isoformat(),
                }
            )
            return
        if message_type == "chat.sync":
            await self._sync(content.get("after_event_id"))
            return
        if message_type == "chat.typing.set":
            await self._set_typing(content)
            return
        await self._error("unsupported_command", "Unsupported chat realtime command.")

    async def chat_realtime(self, event):
        await self.send_json(event["event"])

    async def chat_typing(self, event):
        await self.send_json(event["event"])

    async def _sync(self, raw_after_event_id):
        if not isinstance(raw_after_event_id, int) or raw_after_event_id < 0:
            await self._error("invalid_cursor", "A non-negative event cursor is required.")
            return
        events = await self._events_after(raw_after_event_id)
        if len(events) > settings.CHAT_REALTIME_REPLAY_LIMIT:
            await self.send_json({"type": "chat.resync_required", "reason": "replay_limit"})
            return
        for event in events:
            await self.send_json(serialize_event(event))

    async def _set_typing(self, content):
        conversation_id = content.get("conversation_id")
        is_typing = content.get("is_typing")
        if not isinstance(conversation_id, int) or conversation_id < 1 or not isinstance(is_typing, bool):
            await self._error("invalid_typing", "A valid conversation and typing state are required.")
            return
        if not await self._can_access(conversation_id):
            await self._error("not_found", "Conversation not found.")
            return
        target_group = user_group(self.user_id) if self.audience == STAFF_AUDIENCE else staff_group()
        await self.channel_layer.group_send(
            target_group,
            {
                "type": "chat.typing",
                "event": {
                    "type": "chat.typing.updated",
                    "conversation_id": conversation_id,
                    "actor_side": "staff" if self.audience == STAFF_AUDIENCE else "user",
                    "is_typing": is_typing,
                    "expires_at": (timezone.now() + timedelta(seconds=5)).isoformat(),
                },
            },
        )

    async def _error(self, code: str, message: str):
        await self.send_json({"type": "chat.error", "code": code, "message": message})

    @database_sync_to_async
    def _latest_event_id(self):
        queryset = ChatRealtimeEvent.objects.filter(audience=self.audience)
        if self.audience == USER_AUDIENCE:
            queryset = queryset.filter(recipient_user_id=self.user_id)
        return queryset.order_by("-id").values_list("id", flat=True).first() or 0

    @database_sync_to_async
    def _events_after(self, event_id: int):
        queryset = ChatRealtimeEvent.objects.filter(audience=self.audience, id__gt=event_id)
        if self.audience == USER_AUDIENCE:
            queryset = queryset.filter(recipient_user_id=self.user_id)
        return list(queryset.order_by("id")[: settings.CHAT_REALTIME_REPLAY_LIMIT + 1])

    @database_sync_to_async
    def _can_access(self, conversation_id: int) -> bool:
        if self.audience == STAFF_AUDIENCE:
            return visible_for_staff().filter(pk=conversation_id).exists()
        return visible_for_user(self.scope["user"]).filter(pk=conversation_id).exists()
