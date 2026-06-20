from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import NotificationType
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

    def __str__(self):
        return f"Notification #{self.id} — {self.title} ({self.get_type_display()})"
