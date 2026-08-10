from __future__ import annotations

from typing import Literal

import pydantic
from django.utils.translation import gettext_lazy as _
from marketplace.services.listings import ordered_photos, photo_url

from core.constants import ChatMessageKind, ListingStatus


class _StrictInput(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatUserOutput(pydantic.BaseModel):
    id: int
    first_name: str
    last_name: str | None
    phone: str | None
    avatar_url: str | None


class ChatListingOutput(pydantic.BaseModel):
    id: int
    property_id: int
    title: str
    cover_image_url: str | None
    price: float | None
    currency: str
    status: str
    is_available: bool


class ChatMessageInput(_StrictInput):
    text: str = pydantic.Field(min_length=1, max_length=1024)
    client_id: str | None = pydantic.Field(default=None, min_length=1, max_length=64)


class ChatImageInput(_StrictInput):
    client_id: str = pydantic.Field(min_length=1, max_length=64)


class ChatReadInput(_StrictInput):
    up_to_message_id: int | None = pydantic.Field(default=None, ge=1)


class ChatConversationListQuery(_StrictInput):
    page: int = pydantic.Field(default=1, ge=1)
    per_page: int = pydantic.Field(default=20, ge=1, le=100)
    status: Literal["open", "archived", "reported", "deleted_by_user"] = "open"
    q: str | None = None
    listing_id: int | None = pydantic.Field(default=None, ge=1)


class ChatMessageQuery(_StrictInput):
    after_id: int | None = pydantic.Field(default=None, ge=0)
    before_id: int | None = pydantic.Field(default=None, ge=1)
    limit: int = pydantic.Field(default=30, ge=1, le=100)


class ChatReportListQuery(_StrictInput):
    resolved: bool | None = None
    page: int = pydantic.Field(default=1, ge=1)
    per_page: int = pydantic.Field(default=20, ge=1, le=100)


class ChatMessageOutput(pydantic.BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    sender_side: str
    sender_name: str
    is_mine: bool
    kind: str
    text: str | None
    image_url: str | None
    image_width: int | None
    image_height: int | None
    image_size_bytes: int | None
    client_id: str | None
    read_at: str | None
    is_read: bool
    created_at: str
    updated_at: str


class ConversationStateOutput(pydantic.BaseModel):
    id: int
    is_read_only: bool
    deleted_by_user: bool
    is_blocked: bool
    is_archived: bool
    is_muted: bool
    unread_count: int
    last_message_id: int | None
    peer_last_read_message_id: int | None
    staff_last_read_message_id: int | None
    listing_is_available: bool


class ConversationOutput(pydantic.BaseModel):
    id: int
    listing_id: int
    listing_title: str
    listing: ChatListingOutput
    user: ChatUserOutput
    last_message: ChatMessageOutput | None
    last_message_id: int | None
    last_message_at: str | None
    user_deleted_at: str | None
    deleted_by_user: bool
    is_read_only: bool
    is_blocked: bool
    is_archived: bool
    is_muted: bool
    listing_is_available: bool
    last_message_preview: str | None
    last_message_kind: str | None
    unread_count: int
    staff_unread_count: int
    user_unread_count: int
    staff_last_read_message_id: int | None
    user_last_read_message_id: int | None
    peer_last_read_message_id: int | None
    report_count: int
    created_at: str
    updated_at: str


class ConversationReportOutput(pydantic.BaseModel):
    id: int
    conversation_id: int
    reported_by_id: int
    reported_by: ChatUserOutput
    reason: str
    note: str
    resolved_at: str | None
    resolved_by_id: int | None
    created_at: str
    updated_at: str


def _iso(value):
    return value.isoformat() if value is not None else None


def _absolute_file_url(file_field, request):
    if not file_field or not getattr(file_field, "name", None):
        return None
    url = file_field.url
    return request.build_absolute_uri(url) if request is not None else url


def _user_name(user):
    return f"{user.first_name} {user.last_name or ''}".strip()


def serialize_user(user, request):
    return ChatUserOutput(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        avatar_url=_absolute_file_url(user.avatar, request),
    ).model_dump(mode="json")


def _listing_is_available(listing):
    return listing.status == ListingStatus.PUBLISHED and listing.deleted_at is None


def _listing_cover_image_url(listing, request):
    for photo in ordered_photos(listing.property):
        if photo.image:
            return photo_url(photo, request)
    return None


def serialize_listing(listing, request):
    property_obj = listing.property
    title = property_obj.name if property_obj is not None else ""
    price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
    return ChatListingOutput(
        id=listing.id,
        property_id=listing.property_id,
        title=title,
        cover_image_url=_listing_cover_image_url(listing, request),
        price=float(price) if price is not None else None,
        currency=listing.currency or property_obj.ask_currency or "",
        status=listing.status,
        is_available=_listing_is_available(listing),
    ).model_dump(mode="json")


def serialize_message(message, request, user):
    return ChatMessageOutput(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_side=message.sender_side,
        sender_name=_user_name(message.sender),
        is_mine=message.sender_id == user.id,
        kind=message.kind,
        text=message.text,
        image_url=_absolute_file_url(message.image, request),
        image_width=message.image_width,
        image_height=message.image_height,
        image_size_bytes=message.image_size_bytes,
        client_id=message.client_id,
        read_at=_iso(message.read_at),
        is_read=message.read_at is not None,
        created_at=message.created_at.isoformat(),
        updated_at=message.updated_at.isoformat(),
    ).model_dump(mode="json")


def serialize_conversation_state(conversation):
    listing = conversation.listing
    return ConversationStateOutput(
        id=conversation.id,
        is_read_only=conversation.user_deleted_at is not None,
        deleted_by_user=conversation.user_deleted_at is not None,
        is_blocked=conversation.is_user_blocked,
        is_archived=conversation.staff_archived_at is not None,
        is_muted=conversation.user_muted,
        unread_count=conversation.staff_unread_count,
        last_message_id=conversation.last_message_id,
        peer_last_read_message_id=conversation.user_last_read_message_id,
        staff_last_read_message_id=conversation.staff_last_read_message_id,
        listing_is_available=_listing_is_available(listing),
    ).model_dump(mode="json")


def serialize_conversation(conversation, request, user):
    listing = conversation.listing
    listing_data = serialize_listing(listing, request)
    last_message = conversation.last_message
    last_message_preview = None
    last_message_kind = None
    if last_message is not None:
        last_message_kind = last_message.kind
        last_message_preview = (
            str(_("Photo")) if last_message.kind == ChatMessageKind.IMAGE else (last_message.text or "")[:120]
        )
    report_count = getattr(conversation, "report_count", None)
    if report_count is None:
        report_count = conversation.reports.count()
    return ConversationOutput(
        id=conversation.id,
        listing_id=conversation.listing_id,
        listing_title=listing_data["title"],
        listing=listing_data,
        user=serialize_user(conversation.user, request),
        last_message=serialize_message(last_message, request, user) if last_message is not None else None,
        last_message_id=conversation.last_message_id,
        last_message_at=_iso(conversation.last_message_at),
        user_deleted_at=_iso(conversation.user_deleted_at),
        deleted_by_user=conversation.user_deleted_at is not None,
        is_read_only=conversation.user_deleted_at is not None,
        is_blocked=conversation.is_user_blocked,
        is_archived=conversation.staff_archived_at is not None,
        is_muted=conversation.user_muted,
        listing_is_available=_listing_is_available(listing),
        last_message_preview=last_message_preview,
        last_message_kind=last_message_kind,
        unread_count=conversation.staff_unread_count,
        staff_unread_count=conversation.staff_unread_count,
        user_unread_count=conversation.user_unread_count,
        staff_last_read_message_id=conversation.staff_last_read_message_id,
        user_last_read_message_id=conversation.user_last_read_message_id,
        peer_last_read_message_id=conversation.user_last_read_message_id,
        report_count=report_count,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    ).model_dump(mode="json")


def serialize_report(report, request):
    return ConversationReportOutput(
        id=report.id,
        conversation_id=report.conversation_id,
        reported_by_id=report.reported_by_id,
        reported_by=serialize_user(report.reported_by, request),
        reason=report.reason,
        note=report.note,
        resolved_at=_iso(report.resolved_at),
        resolved_by_id=report.resolved_by_id,
        created_at=report.created_at.isoformat(),
        updated_at=report.updated_at.isoformat(),
    ).model_dump(mode="json")
