from __future__ import annotations

import json
from http import HTTPStatus

import pydantic
from chat.exceptions import ChatReadOnlyError
from chat.models import ConversationReport, Message
from chat.services import (
    assert_staff_can_write,
    get_for_staff_or_404,
    mark_read,
    purge,
    send_message,
    set_archived,
    set_blocked,
    validate_chat_image,
    visible_for_staff,
)
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query

from api.v1.chat.schemas import (
    ChatConversationListQuery,
    ChatImageInput,
    ChatMessageInput,
    ChatMessageQuery,
    ChatReadInput,
    ChatReportListQuery,
    serialize_conversation,
    serialize_conversation_state,
    serialize_message,
    serialize_report,
)
from api.v1.management.views import ManagementView
from core.api.views import DetailPath
from core.constants import ChatSenderSide
from core.utils.pagination import build_paginated_response_from_queryset
from core.utils.uploads import UploadError


class ChatManagementView(ManagementView):
    def _parse_optional_body(self, schema):
        raw_body = getattr(self.request, "body", b"") or b""
        if not raw_body:
            return schema()
        try:
            payload = json.loads(raw_body)
        except TypeError, ValueError:
            return self.fail(
                error=str(_("Invalid JSON body")),
                message=str(_("Validation error")),
            )
        try:
            return schema.model_validate(payload)
        except pydantic.ValidationError as err:
            raw_errors = err.errors(include_url=False)
            for item in raw_errors:
                item.pop("ctx", None)
            return self.fail(error=raw_errors, message=str(_("Validation error")))

    def _conversation(self, parsed_path: Path[DetailPath]):
        return get_for_staff_or_404(parsed_path.pk)

    @staticmethod
    def _read_only_failure(error):
        return ChatManagementView.fail(
            error=str(error),
            message=str(_("Conversation is read-only")),
            status_code=HTTPStatus.CONFLICT,
        )


class ConversationListView(ChatManagementView):
    def get(self, parsed_query: Query[ChatConversationListQuery]) -> dict:
        queryset = (
            visible_for_staff()
            .select_related("last_message__sender")
            .prefetch_related("listing__property__photos")
            .annotate(
                report_count=Count("reports", distinct=True),
                unresolved_report_count=Count(
                    "reports",
                    filter=Q(reports__resolved_at__isnull=True),
                    distinct=True,
                ),
            )
            # Explicit total order: -last_message_at alone leaves ties (and NULLs
            # for conversations with no messages), which makes cursor-free
            # pagination non-deterministic across pages.
            .order_by("-last_message_at", "-id")
        )

        if parsed_query.status == "archived":
            queryset = queryset.filter(staff_archived_at__isnull=False)
        elif parsed_query.status == "reported":
            # NOT reports__resolved_at__isnull=True: that is a LEFT JOIN, so it
            # also matches conversations with no reports at all.
            queryset = queryset.filter(unresolved_report_count__gt=0)
        elif parsed_query.status == "deleted_by_user":
            queryset = queryset.filter(user_deleted_at__isnull=False)
        else:
            queryset = queryset.filter(staff_archived_at__isnull=True)

        if parsed_query.listing_id is not None:
            queryset = queryset.filter(listing_id=parsed_query.listing_id)
        if parsed_query.q:
            queryset = queryset.filter(
                Q(listing__property__name__icontains=parsed_query.q)
                | Q(user__first_name__icontains=parsed_query.q)
                | Q(user__last_name__icontains=parsed_query.q)
                | Q(user__phone__icontains=parsed_query.q)
            )

        paginated = build_paginated_response_from_queryset(
            queryset,
            parsed_query.page,
            parsed_query.per_page,
            lambda conversation: serialize_conversation(conversation, self.request, self.request.user),
        )
        return self.ok(paginated)


class ConversationDetailView(ChatManagementView):
    def get(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self._conversation(parsed_path)
        return self.ok(serialize_conversation(conversation, self.request, self.request.user))

    def delete(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self._conversation(parsed_path)
        conversation_id = conversation.id
        purge(conversation)
        return self.ok({"id": conversation_id, "deleted": True}, status_code=HTTPStatus.OK)


class ConversationMessagesView(ChatManagementView):
    def get(self, parsed_path: Path[DetailPath], parsed_query: Query[ChatMessageQuery]) -> dict:
        conversation = self._conversation(parsed_path)
        queryset = Message.objects.filter(conversation=conversation).select_related("sender")

        if parsed_query.after_id is not None and parsed_query.before_id is not None:
            return self.fail(
                error=str(_("Use either after_id or before_id, not both")),
                message=str(_("Validation error")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        if parsed_query.after_id is not None:
            rows = list(queryset.filter(id__gt=parsed_query.after_id).order_by("id")[: parsed_query.limit + 1])
            has_more = len(rows) > parsed_query.limit
            if has_more:
                rows = rows[: parsed_query.limit]
        elif parsed_query.before_id is not None:
            rows = list(queryset.filter(id__lt=parsed_query.before_id).order_by("-id")[: parsed_query.limit + 1])
            has_more = len(rows) > parsed_query.limit
            if has_more:
                rows = rows[: parsed_query.limit]
            rows.reverse()
        else:
            rows = list(queryset.order_by("-id")[: parsed_query.limit + 1])
            has_more = len(rows) > parsed_query.limit
            if has_more:
                rows = rows[: parsed_query.limit]
            rows.reverse()

        data = {
            "messages": [serialize_message(message, self.request, self.request.user) for message in rows],
            "has_more": has_more,
            "conversation": serialize_conversation_state(conversation),
        }
        response = self.ok(data, status_code=HTTPStatus.OK)
        response["Cache-Control"] = "no-store"
        return response

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[ChatMessageInput]) -> dict:
        conversation = self._conversation(parsed_path)
        try:
            assert_staff_can_write(conversation)
            message, created = send_message(
                conversation,
                sender=self.request.user,
                side=ChatSenderSide.STAFF,
                text=parsed_body.text,
                client_id=parsed_body.client_id,
            )
        except ChatReadOnlyError as error:
            return self._read_only_failure(error)

        return self.ok(
            serialize_message(message, self.request, self.request.user),
            status_code=HTTPStatus.CREATED if created else HTTPStatus.OK,
        )


class ConversationImageMessageCreateView(ChatManagementView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self._conversation(parsed_path)
        try:
            assert_staff_can_write(conversation)
        except ChatReadOnlyError as error:
            return self._read_only_failure(error)

        image = self.request.FILES.get("image")
        if image is None:
            return self.fail(error=str(_("No image provided")))

        try:
            parsed_input = ChatImageInput.model_validate({"client_id": self.request.POST.get("client_id")})
        except pydantic.ValidationError as err:
            raw_errors = err.errors(include_url=False)
            for item in raw_errors:
                item.pop("ctx", None)
            return self.fail(error=raw_errors, message=str(_("Validation error")))

        try:
            validate_chat_image(image)
        except UploadError as error:
            return self.fail(error=str(error), message=str(_("Upload failed")))

        try:
            message, _created = send_message(
                conversation,
                sender=self.request.user,
                side=ChatSenderSide.STAFF,
                image=image,
                client_id=parsed_input.client_id,
            )
        except ChatReadOnlyError as error:
            return self._read_only_failure(error)

        return self.ok(
            serialize_message(message, self.request, self.request.user),
            status_code=HTTPStatus.CREATED,
        )


class ConversationReadView(ChatManagementView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self._conversation(parsed_path)
        parsed_body = self._parse_optional_body(ChatReadInput)
        mark_read(
            conversation,
            side=ChatSenderSide.STAFF,
            up_to_message_id=parsed_body.up_to_message_id,
        )
        return self.ok(
            serialize_conversation(conversation, self.request, self.request.user),
            status_code=HTTPStatus.OK,
        )


class ConversationArchiveView(ChatManagementView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self._conversation(parsed_path)
        set_archived(conversation, side=ChatSenderSide.STAFF, value=True)
        return self.ok(
            serialize_conversation(conversation, self.request, self.request.user),
            status_code=HTTPStatus.OK,
        )


class ConversationUnarchiveView(ChatManagementView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self._conversation(parsed_path)
        set_archived(conversation, side=ChatSenderSide.STAFF, value=False)
        return self.ok(
            serialize_conversation(conversation, self.request, self.request.user),
            status_code=HTTPStatus.OK,
        )


class ConversationBlockView(ChatManagementView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self._conversation(parsed_path)
        set_blocked(conversation, staff_user=self.request.user, value=True)
        return self.ok(
            serialize_conversation(conversation, self.request, self.request.user),
            status_code=HTTPStatus.OK,
        )


class ConversationUnblockView(ChatManagementView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        conversation = self._conversation(parsed_path)
        set_blocked(conversation, staff_user=self.request.user, value=False)
        return self.ok(
            serialize_conversation(conversation, self.request, self.request.user),
            status_code=HTTPStatus.OK,
        )


class ReportListView(ChatManagementView):
    def get(self, parsed_query: Query[ChatReportListQuery]) -> dict:
        queryset = ConversationReport.objects.select_related(
            "conversation__listing__property",
            "conversation__user",
            "reported_by",
            "resolved_by",
        ).order_by("-created_at", "-id")
        if parsed_query.resolved is not None:
            queryset = queryset.filter(resolved_at__isnull=not parsed_query.resolved)
        paginated = build_paginated_response_from_queryset(
            queryset,
            parsed_query.page,
            parsed_query.per_page,
            lambda report: serialize_report(report, self.request),
        )
        return self.ok(paginated)


class ReportResolveView(ChatManagementView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        report = get_object_or_404(
            ConversationReport.objects.select_related("reported_by", "resolved_by"),
            pk=parsed_path.pk,
        )
        if report.resolved_at is None:
            report.resolved_at = timezone.now()
            report.resolved_by = self.request.user
            report.save(update_fields=["resolved_at", "resolved_by", "updated_at"])
        return self.ok(serialize_report(report, self.request), status_code=HTTPStatus.OK)
