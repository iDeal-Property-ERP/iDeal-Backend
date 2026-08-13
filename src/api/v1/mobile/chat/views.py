from __future__ import annotations

from http import HTTPStatus

from chat.exceptions import ChatReadOnlyError, ChatUnavailableError
from chat.models import Message
from chat.services import (
    delete_for_user,
    get_for_user_or_404,
    mark_read,
    open_or_get,
    report,
    send_message,
    set_archived,
    set_muted,
    validate_chat_image,
    visible_for_user,
)
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from marketplace.models import Listing
from marketplace.services.listings import ordered_photos, photo_url, photo_variant_url

from api.v1.mobile.chat.schemas import (
    ChatListingRefOutput,
    ChatMessageOutput,
    ConversationListQuery,
    ConversationOutput,
    ConversationReportOutput,
    ConversationStateOutput,
    MarkReadInput,
    MessagesQuery,
    OpenConversationInput,
    ReportConversationInput,
    SendTextMessageInput,
    SummaryOutput,
    SummaryQuery,
)
from core.api.views import BaseController, DetailPath
from core.constants import ChatMessageKind, ChatSenderSide, ListingStatus
from core.utils.pagination import build_paginated_response_from_queryset
from core.utils.uploads import UploadError


def _listing_is_available(listing) -> bool:
    return listing.status == ListingStatus.PUBLISHED and listing.deleted_at is None


def _listing_cover_photo(listing):
    photos = ordered_photos(listing.property)
    return next((item for item in photos if item.image), None)


def _serialize_listing(listing, request) -> dict:
    property_obj = listing.property
    price = listing.monthly_price if listing.monthly_price is not None else listing.listed_price
    cover_photo = _listing_cover_photo(listing)
    return ChatListingRefOutput(
        id=listing.id,
        title=property_obj.name,
        cover_image_url=photo_url(cover_photo, request) if cover_photo else None,
        cover_preview_url=photo_variant_url(cover_photo, "preview_image", request) if cover_photo else None,
        cover_display_url=photo_variant_url(cover_photo, "display_image", request) if cover_photo else None,
        price=float(price) if price is not None else None,
        currency=listing.currency or property_obj.ask_currency or "",
        is_available=_listing_is_available(listing),
    ).model_dump(mode="json")


def serialize_message(message, request, user) -> dict:
    image_url = request.build_absolute_uri(message.image.url) if message.image else None
    return ChatMessageOutput(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_side=message.sender_side,
        is_mine=message.sender_id == user.id,
        kind=message.kind,
        text=message.text,
        image_url=image_url,
        image_width=message.image_width,
        image_height=message.image_height,
        client_id=message.client_id,
        is_read=message.read_at is not None,
        created_at=message.created_at.isoformat(),
    ).model_dump(mode="json")


def serialize_conversation_state(conversation) -> dict:
    return ConversationStateOutput(
        id=conversation.id,
        is_read_only=conversation.is_user_blocked,
        deleted_by_peer=bool(getattr(conversation, "staff_deleted_at", None)),
        is_blocked=conversation.is_user_blocked,
        is_archived=conversation.user_archived_at is not None,
        is_muted=conversation.user_muted,
        unread_count=conversation.user_unread_count,
        last_message_id=conversation.last_message_id,
        peer_last_read_message_id=conversation.staff_last_read_message_id,
        listing_is_available=_listing_is_available(conversation.listing),
    ).model_dump(mode="json")


def serialize_conversation(conversation, request) -> dict:
    last_message = conversation.last_message
    last_message_kind = last_message.kind if last_message is not None else None
    if last_message is None:
        last_message_preview = None
    elif last_message.kind == ChatMessageKind.IMAGE:
        last_message_preview = str(_("Photo"))
    else:
        last_message_preview = (last_message.text or "")[:120]

    return ConversationOutput(
        **serialize_conversation_state(conversation),
        listing=_serialize_listing(conversation.listing, request),
        last_message_preview=last_message_preview,
        last_message_kind=last_message_kind,
        last_message_at=conversation.last_message_at.isoformat() if conversation.last_message_at else None,
        updated_at=conversation.updated_at.isoformat(),
    ).model_dump(mode="json")


def _serialize_report(conversation_report) -> dict:
    return ConversationReportOutput(
        id=conversation_report.id,
        conversation_id=conversation_report.conversation_id,
        reason=conversation_report.reason,
        note=conversation_report.note,
        created_at=conversation_report.created_at.isoformat(),
    ).model_dump(mode="json")


def _chat_failure(controller, error):
    if isinstance(error, ChatUnavailableError):
        return controller.fail(
            error=str(error),
            message=str(_("Chat is unavailable")),
            status_code=HTTPStatus.BAD_REQUEST,
        )
    return controller.fail(
        error=str(error),
        message=str(_("Chat is read-only")),
        status_code=HTTPStatus.CONFLICT,
    )


class MobileConversationController(BaseController):
    def get_conversation(self, parsed_path: Path[DetailPath]):
        return get_for_user_or_404(parsed_path.pk, self.request.user)


class ConversationCollectionView(MobileConversationController):
    def post(self, parsed_body: Body[OpenConversationInput]) -> dict:
        listing = Listing.global_objects.select_related("property").filter(pk=parsed_body.listing_id).first()
        if listing is None:
            return self.fail(
                error=str(_("Listing not found")),
                message=str(_("Not found")),
                status_code=HTTPStatus.NOT_FOUND,
            )

        try:
            conversation, created = open_or_get(listing, self.request.user)
        except ChatUnavailableError as error:
            return _chat_failure(self, error)

        conversation = get_for_user_or_404(conversation.id, self.request.user)
        data = serialize_conversation(conversation, self.request)
        status_code = HTTPStatus.CREATED if created else HTTPStatus.OK
        return self.ok(data, status_code=status_code)

    def get(self, parsed_query: Query[ConversationListQuery]) -> dict:
        # Explicit total order: -last_message_at alone leaves ties (and NULLs for
        # conversations with no messages), which makes paging non-deterministic.
        queryset = visible_for_user(self.request.user).order_by("-last_message_at", "-id")
        if parsed_query.archived:
            queryset = queryset.filter(user_archived_at__isnull=False)
        else:
            queryset = queryset.filter(user_archived_at__isnull=True)

        paginated = build_paginated_response_from_queryset(
            queryset,
            parsed_query.page or 1,
            parsed_query.per_page,
            lambda conversation: serialize_conversation(conversation, self.request),
        )
        return self.ok(paginated)


class ChatSummaryView(BaseController):
    def get(self, parsed_query: Query[SummaryQuery]) -> dict:
        queryset = visible_for_user(self.request.user)
        total_unread = queryset.aggregate(total=Sum("user_unread_count"))["total"] or 0
        changed_conversation_ids = []

        if parsed_query.since is not None:
            since = parsed_query.since
            if timezone.is_naive(since):
                since = timezone.make_aware(since)
            changed_conversation_ids = list(
                queryset.filter(updated_at__gt=since).order_by("-updated_at", "-id").values_list("id", flat=True)[:100]
            )

        data = SummaryOutput(
            total_unread=total_unread,
            changed_conversation_ids=changed_conversation_ids,
            server_time=timezone.now().isoformat(),
        ).model_dump(mode="json")
        return self.ok(data)


class ConversationDetailView(MobileConversationController):
    def get(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self.get_conversation(parsed_path)
        return self.ok(serialize_conversation(conversation, self.request))

    def delete(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self.get_conversation(parsed_path)
        delete_for_user(conversation, self.request.user)
        return self.ok({"id": conversation.id, "deleted": True}, status_code=HTTPStatus.OK)


class ConversationMessagesView(MobileConversationController):
    def get(self, parsed_path: Path[DetailPath], parsed_query: Query[MessagesQuery]) -> dict:
        conversation = self.get_conversation(parsed_path)
        if parsed_query.after_id is not None and parsed_query.before_id is not None:
            return self.fail(
                error=str(_("Use either after_id or before_id, not both.")),
                message=str(_("Validation error")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        limit = min(max(parsed_query.limit, 1), 100)
        queryset = Message.objects.filter(conversation=conversation).select_related("sender")
        if parsed_query.after_id is not None:
            messages = list(queryset.filter(id__gt=parsed_query.after_id).order_by("id")[: limit + 1])
            has_more = len(messages) > limit
            messages = messages[:limit]
        elif parsed_query.before_id is not None:
            messages = list(queryset.filter(id__lt=parsed_query.before_id).order_by("-id")[: limit + 1])
            has_more = len(messages) > limit
            messages = list(reversed(messages[:limit]))
        else:
            messages = list(queryset.order_by("-id")[: limit + 1])
            has_more = len(messages) > limit
            messages = list(reversed(messages[:limit]))

        data = {
            "messages": [serialize_message(message, self.request, self.request.user) for message in messages],
            "has_more": has_more,
            "conversation": serialize_conversation_state(conversation),
        }
        response = self.ok(data, status_code=HTTPStatus.OK)
        response["Cache-Control"] = "no-store"
        return response

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[SendTextMessageInput]) -> dict:
        conversation = self.get_conversation(parsed_path)
        try:
            message, created = send_message(
                conversation,
                sender=self.request.user,
                side=ChatSenderSide.USER,
                text=parsed_body.text,
                client_id=parsed_body.client_id,
            )
        except ChatReadOnlyError as error:
            return _chat_failure(self, error)

        status_code = HTTPStatus.CREATED if created else HTTPStatus.OK
        return self.ok(
            serialize_message(message, self.request, self.request.user),
            status_code=status_code,
        )


class ConversationImageMessageView(MobileConversationController):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self.get_conversation(parsed_path)
        image = self.request.FILES.get("image")
        if image is None:
            return self.fail(
                error=str(_("No image provided")),
                message=str(_("Validation error")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        client_id = (self.request.POST.get("client_id") or "").strip() or None
        if client_id is not None and len(client_id) > 64:
            return self.fail(
                error=str(_("Client ID is too long")),
                message=str(_("Validation error")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        try:
            validate_chat_image(image)
        except UploadError as error:
            return self.fail(
                error=str(error),
                message=str(_("Upload failed")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        try:
            message, _created = send_message(
                conversation,
                sender=self.request.user,
                side=ChatSenderSide.USER,
                image=image,
                client_id=client_id,
            )
        except ChatReadOnlyError as error:
            return _chat_failure(self, error)

        return self.ok(
            serialize_message(message, self.request, self.request.user),
            status_code=HTTPStatus.CREATED,
        )


class ConversationReadView(MobileConversationController):
    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[MarkReadInput]) -> dict:
        conversation = self.get_conversation(parsed_path)
        mark_read(
            conversation,
            side=ChatSenderSide.USER,
            up_to_message_id=parsed_body.up_to_message_id,
        )
        return self.ok(serialize_conversation_state(conversation), status_code=HTTPStatus.OK)


class ConversationArchiveView(MobileConversationController):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self.get_conversation(parsed_path)
        set_archived(conversation, side=ChatSenderSide.USER, value=True)
        return self.ok(serialize_conversation_state(conversation), status_code=HTTPStatus.OK)


class ConversationUnarchiveView(MobileConversationController):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self.get_conversation(parsed_path)
        set_archived(conversation, side=ChatSenderSide.USER, value=False)
        return self.ok(serialize_conversation_state(conversation), status_code=HTTPStatus.OK)


class ConversationMuteView(MobileConversationController):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self.get_conversation(parsed_path)
        set_muted(conversation, True)
        return self.ok(serialize_conversation_state(conversation), status_code=HTTPStatus.OK)


class ConversationUnmuteView(MobileConversationController):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self.get_conversation(parsed_path)
        set_muted(conversation, False)
        return self.ok(serialize_conversation_state(conversation), status_code=HTTPStatus.OK)


class ConversationReportView(MobileConversationController):
    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[ReportConversationInput]) -> dict:
        conversation = self.get_conversation(parsed_path)
        conversation_report = report(
            conversation,
            reported_by=self.request.user,
            reason=parsed_body.reason,
            note=parsed_body.note or "",
        )
        return self.ok(_serialize_report(conversation_report), status_code=HTTPStatus.CREATED)
