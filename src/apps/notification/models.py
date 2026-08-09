from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import (
    DevicePlatform,
    NotificationAudience,
    NotificationCategory,
    NotificationType,
    category_for_notification_type,
)
from core.models import SoftDeleteModel, TimestampedModel


class Notification(TimestampedModel, SoftDeleteModel):
    recipient = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="notifications",
        verbose_name=_("Recipient"),
    )
    type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.GENERAL,
        verbose_name=_("Type"),
    )
    audience = models.CharField(
        max_length=10,
        choices=NotificationAudience.choices,
        default=NotificationAudience.BOTH,
        db_index=True,
        verbose_name=_("Audience"),
    )
    title = models.CharField(max_length=200, verbose_name=_("Title"))
    body = models.TextField(null=True, blank=True, verbose_name=_("Body"))
    related_object_type = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Related Object Type"))
    related_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Related Object ID"))
    is_read = models.BooleanField(default=False, db_index=True, verbose_name=_("Is Read"))
    read_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Read At"))

    class Meta:
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ["-created_at"]
        db_table = "notifications"
        indexes = [
            models.Index(fields=["recipient"]),
            models.Index(fields=["is_read"]),
            models.Index(fields=["type"]),
        ]

    @property
    def category(self) -> str:
        return category_for_notification_type(self.type)

    def __str__(self):
        return f"Notification #{self.id} — {self.title} ({self.get_type_display()})"


class DeviceToken(TimestampedModel, SoftDeleteModel):
    user = models.ForeignKey(
        "account.User",
        on_delete=models.CASCADE,
        related_name="device_tokens",
        verbose_name=_("User"),
    )
    token = models.TextField(unique=True, verbose_name=_("Token"))
    platform = models.CharField(
        max_length=10,
        choices=DevicePlatform.choices,
        verbose_name=_("Platform"),
    )
    device_id = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Device ID"))
    app_version = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("App Version"))
    locale = models.CharField(max_length=10, null=True, blank=True, verbose_name=_("Locale"))
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Is Active"))
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Last Seen At"))

    class Meta:
        verbose_name = _("Device Token")
        verbose_name_plural = _("Device Tokens")
        db_table = "notification_device_tokens"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.get_platform_display()} device for user #{self.user_id}"


NOTIFICATION_CATEGORY_PREFERENCE_FIELDS = {
    NotificationCategory.PAYMENTS: "payments_enabled",
    NotificationCategory.BOOKINGS: "bookings_enabled",
    NotificationCategory.MAINTENANCE: "maintenance_enabled",
    NotificationCategory.LEASES: "leases_enabled",
    NotificationCategory.GENERAL: "general_enabled",
}


class NotificationPreference(TimestampedModel, SoftDeleteModel):
    user = models.OneToOneField(
        "account.User",
        on_delete=models.CASCADE,
        related_name="notification_preference",
        verbose_name=_("User"),
    )
    push_enabled = models.BooleanField(default=True, verbose_name=_("Push Enabled"))
    payments_enabled = models.BooleanField(default=True, verbose_name=_("Payments Enabled"))
    bookings_enabled = models.BooleanField(default=True, verbose_name=_("Bookings Enabled"))
    maintenance_enabled = models.BooleanField(default=True, verbose_name=_("Maintenance Enabled"))
    leases_enabled = models.BooleanField(default=True, verbose_name=_("Leases Enabled"))
    general_enabled = models.BooleanField(default=True, verbose_name=_("General Enabled"))

    class Meta:
        verbose_name = _("Notification Preference")
        verbose_name_plural = _("Notification Preferences")
        db_table = "notification_preferences"

    def allows_category(self, category: str) -> bool:
        """Return whether push is enabled globally and for the given category."""
        field_name = NOTIFICATION_CATEGORY_PREFERENCE_FIELDS.get(category, "general_enabled")
        return bool(self.push_enabled and getattr(self, field_name))
