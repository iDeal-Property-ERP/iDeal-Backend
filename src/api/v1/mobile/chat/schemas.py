from __future__ import annotations

from datetime import datetime
from typing import Literal

import pydantic


class ChatListingRefOutput(pydantic.BaseModel):
    id: int
    title: str
    cover_image_url: str | None
    price: float | None
    currency: str
    is_available: bool

    model_config = pydantic.ConfigDict(from_attributes=True)


class ChatMessageOutput(pydantic.BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    sender_side: str
    is_mine: bool
    kind: str
    text: str | None
    image_url: str | None
    image_width: int | None
    image_height: int | None
    client_id: str | None
    is_read: bool
    created_at: str

    model_config = pydantic.ConfigDict(from_attributes=True)


class ConversationStateOutput(pydantic.BaseModel):
    id: int
    is_read_only: bool
    deleted_by_peer: bool
    is_blocked: bool
    is_archived: bool
    is_muted: bool
    unread_count: int
    last_message_id: int | None
    peer_last_read_message_id: int | None
    listing_is_available: bool

    model_config = pydantic.ConfigDict(from_attributes=True)


class ConversationOutput(ConversationStateOutput):
    listing: ChatListingRefOutput
    last_message_preview: str | None
    last_message_kind: str | None
    last_message_at: str | None
    updated_at: str


class ConversationReportOutput(pydantic.BaseModel):
    id: int
    conversation_id: int
    reason: str
    note: str
    created_at: str

    model_config = pydantic.ConfigDict(from_attributes=True)


class SummaryOutput(pydantic.BaseModel):
    total_unread: int
    changed_conversation_ids: list[int]
    server_time: str


class _StrictInput(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid", str_strip_whitespace=True)


class OpenConversationInput(_StrictInput):
    listing_id: int


class SendTextMessageInput(_StrictInput):
    text: str = pydantic.Field(min_length=1, max_length=1024)
    client_id: str | None = pydantic.Field(default=None, max_length=64)


class MarkReadInput(_StrictInput):
    up_to_message_id: int | None = pydantic.Field(default=None, ge=1)


class ReportConversationInput(_StrictInput):
    reason: Literal["spam", "abuse", "scam", "other"]
    note: str | None = pydantic.Field(default=None, max_length=500)


class MessagesQuery(_StrictInput):
    after_id: int | None = pydantic.Field(default=None, ge=1)
    before_id: int | None = pydantic.Field(default=None, ge=1)
    limit: int = 30


class ConversationListQuery(_StrictInput):
    archived: bool = False
    page: int | None = pydantic.Field(default=None, ge=1)
    per_page: int = pydantic.Field(default=20, ge=1)


class SummaryQuery(_StrictInput):
    since: datetime | None = None
