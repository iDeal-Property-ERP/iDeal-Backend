from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import BaseSoftDeleteModelAdmin

from .models import Conversation, ConversationReport, Message


@admin.register(Conversation)
class ConversationAdmin(BaseSoftDeleteModelAdmin):
    list_display = (
        "id",
        "listing",
        "user",
        "last_message_at",
        "user_unread_count",
        "staff_unread_count",
        "user_deleted_at",
        "is_user_blocked",
    )
    list_filter = ("is_user_blocked", "staff_archived_at", "user_archived_at")
    search_fields = (
        "user__phone",
        "user__first_name",
        "user__last_name",
        "listing__property__name",
    )
    raw_id_fields = ("listing", "user", "blocked_by", "last_message")
    readonly_fields = (
        "user_unread_count",
        "staff_unread_count",
        "user_last_read_message_id",
        "staff_last_read_message_id",
        "last_message",
        "last_message_at",
    )
    list_select_related = ("listing", "user", "blocked_by", "last_message")
    fieldsets = (
        (_("Participants"), {"fields": ("listing", "user")}),
        (
            _("User State"),
            {
                "fields": (
                    "user_archived_at",
                    "user_deleted_at",
                    "user_muted",
                    "user_last_read_message_id",
                    "user_unread_count",
                )
            },
        ),
        (
            _("Staff State"),
            {
                "fields": (
                    "staff_archived_at",
                    "staff_last_read_message_id",
                    "staff_unread_count",
                )
            },
        ),
        (
            _("Block State"),
            {"fields": ("is_user_blocked", "blocked_by", "blocked_at")},
        ),
        (
            _("Denormalized State"),
            {"fields": ("last_message", "last_message_at")},
        ),
    )


@admin.register(Message)
class MessageAdmin(BaseSoftDeleteModelAdmin):
    list_display = (
        "id",
        "conversation",
        "sender",
        "sender_side",
        "kind",
        "text",
        "client_id",
        "read_at",
        "created_at",
    )
    list_filter = ("sender_side", "kind", "read_at")
    search_fields = ("text", "client_id", "sender__phone", "sender__first_name", "sender__last_name")
    raw_id_fields = ("conversation", "sender")
    list_select_related = ("conversation", "sender")
    fieldsets = (
        (_("Message Info"), {"fields": ("conversation", "sender", "sender_side", "kind", "text", "client_id")}),
        (_("Image"), {"fields": ("image", "image_width", "image_height", "image_size_bytes")}),
        (_("Read State"), {"fields": ("read_at",)}),
    )


@admin.register(ConversationReport)
class ConversationReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversation",
        "reported_by",
        "reason",
        "resolved_at",
        "resolved_by",
        "created_at",
    )
    list_filter = ("reason", "resolved_at")
    search_fields = (
        "note",
        "reported_by__phone",
        "reported_by__first_name",
        "reported_by__last_name",
        "conversation__listing__property__name",
    )
    raw_id_fields = ("conversation", "reported_by", "resolved_by")
    list_select_related = ("conversation", "reported_by", "resolved_by")
    fieldsets = (
        (_("Report Info"), {"fields": ("conversation", "reported_by", "reason", "note")}),
        (_("Resolution"), {"fields": ("resolved_at", "resolved_by")}),
    )
