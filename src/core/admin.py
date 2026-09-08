from typing import Any

from django.contrib import admin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_softdelete.admin import (
    HARD_DELETE_ACTION,
    REGULAR_DELETE_ACTION_NAME,
    RESTORE_ACTION,
    SOFT_DELETE_ACTION,
)
from django_softdelete.filters import SoftDeleteFilter
from unfold.admin import ModelAdmin

from core.constants import SupportInquiryStatus
from core.models import SupportInquiry


class BaseModelAdmin(ModelAdmin):
    pass


@admin.register(SupportInquiry)
class SupportInquiryAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "name",
        "email",
        "status",
        "created_at",
        "resolved_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("name", "email", "message", "admin_notes")
    readonly_fields = ("created_at", "updated_at", "ip_address", "user_agent")
    ordering = ("-created_at",)
    fieldsets = (
        (_("Inquiry Info"), {"fields": ("name", "email", "message")}),
        (_("Status & Resolution"), {"fields": ("status", "admin_notes", "resolved_at")}),
        (_("Metadata"), {"fields": ("ip_address", "user_agent", "created_at", "updated_at")}),
    )
    actions = ("mark_in_progress", "mark_resolved", "mark_spam")

    @admin.action(description=_("Mark selected inquiries as In Progress"))
    def mark_in_progress(self, request, queryset):
        queryset.update(status=SupportInquiryStatus.IN_PROGRESS)

    @admin.action(description=_("Mark selected inquiries as Resolved"))
    def mark_resolved(self, request, queryset):
        queryset.update(status=SupportInquiryStatus.RESOLVED, resolved_at=timezone.now())

    @admin.action(description=_("Mark selected inquiries as Spam"))
    def mark_spam(self, request, queryset):
        queryset.update(status=SupportInquiryStatus.SPAM)


class BaseSoftDeleteModelAdmin(BaseModelAdmin):
    def get_queryset(self, request) -> Any:
        return self.model.global_objects.get_queryset()

    def get_list_filter(self, request) -> Any:
        list_filter = super().get_list_filter(request) or []
        if not isinstance(list_filter, list):
            list_filter = list(list_filter)
        list_filter.append(SoftDeleteFilter)
        return list_filter

    def get_actions(self, request) -> Any:
        actions = super().get_actions(request)
        actions.pop(REGULAR_DELETE_ACTION_NAME, None)

        deleted_filter_value = {
            "true": "TRUE",
            "false": "FALSE",
            "all": "ALL",
        }[request.GET.get("is_deleted") or "all"]

        if deleted_filter_value == "TRUE":
            actions.update(RESTORE_ACTION)
            actions.update(HARD_DELETE_ACTION)
        elif deleted_filter_value == "FALSE":
            actions.update(SOFT_DELETE_ACTION)
        elif deleted_filter_value == "ALL":
            actions.update(SOFT_DELETE_ACTION)
            actions.update(RESTORE_ACTION)
            actions.update(HARD_DELETE_ACTION)

        return actions
