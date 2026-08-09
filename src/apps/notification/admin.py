from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from notification.models import DeviceToken, Notification, NotificationPreference

from core.admin import BaseSoftDeleteModelAdmin


@admin.register(Notification)
class NotificationAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "recipient", "type", "audience", "title", "is_read", "created_at", "is_deleted")
    list_filter = ("type", "audience", "is_read")
    search_fields = ("title", "body", "recipient__first_name", "recipient__last_name")
    ordering = ("-created_at",)
    fieldsets = (
        (_("Notification Info"), {"fields": ("recipient", "type", "audience", "title", "body")}),
        (_("Related Object"), {"fields": ("related_object_type", "related_object_id")}),
        (_("Status"), {"fields": ("is_read", "read_at")}),
    )


@admin.register(DeviceToken)
class DeviceTokenAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "user", "platform", "device_id", "is_active", "last_seen_at", "created_at", "is_deleted")
    list_filter = ("platform", "is_active")
    search_fields = ("token", "device_id", "user__first_name", "user__last_name")
    ordering = ("-created_at",)
    fieldsets = (
        (_("Device Info"), {"fields": ("user", "token", "platform", "device_id", "app_version", "locale")}),
        (_("Status"), {"fields": ("is_active", "last_seen_at")}),
    )


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(BaseSoftDeleteModelAdmin):
    list_display = (
        "id",
        "user",
        "push_enabled",
        "payments_enabled",
        "bookings_enabled",
        "maintenance_enabled",
        "leases_enabled",
        "general_enabled",
        "is_deleted",
    )
    list_filter = (
        "push_enabled",
        "payments_enabled",
        "bookings_enabled",
        "maintenance_enabled",
        "leases_enabled",
        "general_enabled",
    )
    search_fields = ("user__first_name", "user__last_name", "user__username")
    fieldsets = (
        (_("Preference Owner"), {"fields": ("user",)}),
        (
            _("Push Preferences"),
            {
                "fields": (
                    "push_enabled",
                    "payments_enabled",
                    "bookings_enabled",
                    "maintenance_enabled",
                    "leases_enabled",
                    "general_enabled",
                )
            },
        ),
    )
