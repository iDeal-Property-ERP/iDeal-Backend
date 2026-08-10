import uuid

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.constants import ChatMessageKind, ChatReportReason, ChatSenderSide
from core.models import SoftDeleteModel, TimestampedModel


def chat_image_upload_to(instance, filename):
    ext = (filename.rsplit(".", 1)[-1] or "jpg").lower()[:8]
    return f"chat/{instance.conversation_id}/{uuid.uuid4().hex}.{ext}"


class Conversation(TimestampedModel, SoftDeleteModel):
    listing = models.ForeignKey(
        "marketplace.Listing",
        on_delete=models.CASCADE,
        related_name="conversations",
        verbose_name=_("Listing"),
    )
    user = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="chat_conversations",
        verbose_name=_("User"),
    )

    user_archived_at = models.DateTimeField(null=True, blank=True, verbose_name=_("User Archived At"))
    user_deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("User Deleted At"),
    )
    user_muted = models.BooleanField(default=False, verbose_name=_("User Muted"))
    user_last_read_message_id = models.BigIntegerField(
        null=True, blank=True, verbose_name=_("User Last Read Message ID")
    )
    user_unread_count = models.PositiveIntegerField(default=0, verbose_name=_("User Unread Count"))

    staff_archived_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Staff Archived At"))
    staff_last_read_message_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Staff Last Read Message ID"),
    )
    staff_unread_count = models.PositiveIntegerField(default=0, verbose_name=_("Staff Unread Count"))

    is_user_blocked = models.BooleanField(default=False, db_index=True, verbose_name=_("Is User Blocked"))
    blocked_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Blocked By"),
    )
    blocked_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Blocked At"))

    last_message = models.ForeignKey(
        "chat.Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Last Message"),
    )
    last_message_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Last Message At"),
    )

    class Meta:
        verbose_name = _("Conversation")
        verbose_name_plural = _("Conversations")
        ordering = ["-last_message_at", "-created_at"]
        db_table = "chat_conversations"
        indexes = [
            models.Index(fields=["listing"]),
            models.Index(fields=["user"]),
            models.Index(fields=["-last_message_at"]),
            models.Index(fields=["updated_at"]),
            models.Index(fields=["user", "user_deleted_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "user"],
                condition=Q(deleted_at__isnull=True),
                name="uniq_conversation_per_listing_user",
            ),
        ]

    def __str__(self):
        return f"Conversation #{self.pk}"


class Message(TimestampedModel, SoftDeleteModel):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name=_("Conversation"),
    )
    sender = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="sent_chat_messages",
        verbose_name=_("Sender"),
    )
    sender_side = models.CharField(
        max_length=10,
        choices=ChatSenderSide.choices,
        verbose_name=_("Sender Side"),
    )
    kind = models.CharField(
        max_length=10,
        choices=ChatMessageKind.choices,
        default=ChatMessageKind.TEXT,
        verbose_name=_("Kind"),
    )
    text = models.CharField(max_length=1024, null=True, blank=True, verbose_name=_("Text"))
    image = models.ImageField(
        upload_to=chat_image_upload_to,
        null=True,
        blank=True,
        width_field="image_width",
        height_field="image_height",
        verbose_name=_("Image"),
    )
    image_width = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Image Width"))
    image_height = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Image Height"))
    image_size_bytes = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Image Size Bytes"))
    client_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name=_("Client ID"),
    )
    read_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Read At"))

    class Meta:
        verbose_name = _("Message")
        verbose_name_plural = _("Messages")
        ordering = ["id"]
        db_table = "chat_messages"
        indexes = [
            models.Index(fields=["conversation", "id"]),
            models.Index(fields=["conversation", "-id"]),
            models.Index(fields=["conversation", "read_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "client_id"],
                condition=Q(client_id__isnull=False),
                name="uniq_chat_message_client_id",
            ),
            models.CheckConstraint(
                condition=(
                    Q(kind=ChatMessageKind.TEXT, text__isnull=False)
                    | (Q(kind=ChatMessageKind.IMAGE) & Q(image__isnull=False) & ~Q(image=""))
                ),
                name="chat_message_payload_matches_kind",
            ),
        ]

    def __str__(self):
        return f"Message #{self.pk}"


class ConversationReport(TimestampedModel):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="reports",
        verbose_name=_("Conversation"),
    )
    reported_by = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="chat_reports",
        verbose_name=_("Reported By"),
    )
    reason = models.CharField(max_length=20, choices=ChatReportReason.choices, verbose_name=_("Reason"))
    note = models.CharField(max_length=500, blank=True, default="", verbose_name=_("Note"))
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Resolved At"))
    resolved_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Resolved By"),
    )

    class Meta:
        verbose_name = _("Conversation Report")
        verbose_name_plural = _("Conversation Reports")
        db_table = "chat_conversation_reports"
        indexes = [
            models.Index(fields=["conversation"]),
            models.Index(fields=["resolved_at"]),
        ]

    def __str__(self):
        return f"Report #{self.pk} for conversation #{self.conversation_id}"
