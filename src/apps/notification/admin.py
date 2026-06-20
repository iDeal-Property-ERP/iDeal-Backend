from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from notification.models import Notification

from core.admin import BaseSoftDeleteModelAdmin


@admin.register(Notification)
class NotificationAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "recipient", "type", "title", "is_read", "created_at", "is_deleted")
    list_filter = ("type", "is_read")
    search_fields = ("title", "body", "recipient__first_name", "recipient__last_name")
    ordering = ("-created_at",)
    fieldsets = (
        (_("Notification Info"), {"fields": ("recipient", "type", "title", "body")}),
        (_("Related Object"), {"fields": ("related_object_type", "related_object_id")}),
        (_("Status"), {"fields": ("is_read", "read_at")}),
    )
