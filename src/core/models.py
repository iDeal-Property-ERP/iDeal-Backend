from django.db import models
from django.utils.translation import gettext_lazy as _
from django_softdelete.models import SoftDeleteModel as DjangoSoftDeleteModel

from core.constants import SupportInquiryStatus
from core.managers import DeletedManager, GlobalManager, SoftDeleteManager


class BaseModel(models.Model):
    objects = models.Manager()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        abstract = True


class TimestampedModel(BaseModel):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        abstract = True


class SoftDeleteModel(DjangoSoftDeleteModel, BaseModel):
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name=_("Deleted At"))
    restored_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Restored At"))
    transaction_id = models.UUIDField(null=True, blank=True, verbose_name=_("Transaction ID"))

    objects = SoftDeleteManager()
    deleted_objects = DeletedManager()
    global_objects = GlobalManager()
    all_objects = GlobalManager()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        abstract = True


class SupportInquiry(TimestampedModel):
    name = models.CharField(max_length=255, verbose_name=_("Full Name"))
    email = models.EmailField(db_index=True, verbose_name=_("Email Address"))
    message = models.TextField(verbose_name=_("Message"))
    status = models.CharField(
        max_length=32,
        choices=SupportInquiryStatus.choices(),
        default=SupportInquiryStatus.NEW,
        db_index=True,
        verbose_name=_("Status"),
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name=_("IP Address"))
    user_agent = models.CharField(max_length=512, blank=True, verbose_name=_("User Agent"))
    admin_notes = models.TextField(blank=True, verbose_name=_("Staff Notes"))
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Resolved At"))

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        verbose_name = _("Support Inquiry")
        verbose_name_plural = _("Support Inquiries")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}> (#{self.pk})"
