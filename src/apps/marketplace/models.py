from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import ViewingRequestStatus
from core.models import SoftDeleteModel, TimestampedModel


class Listing(TimestampedModel, SoftDeleteModel):
    property = models.OneToOneField("property.Property", on_delete=models.CASCADE, related_name="listing")
    owner_agreement = models.ForeignKey(
        "contract.OwnerAgreement", on_delete=models.SET_NULL, null=True, blank=True, related_name="listings"
    )
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    description = models.TextField(null=True, blank=True)
    listed_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = _("Listing")
        verbose_name_plural = _("Listings")
        ordering = ["-is_featured", "-created_at"]
        db_table = "listings"
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_featured"]),
        ]

    def __str__(self):
        return f"Listing #{self.id} — {self.property.name}"


class ViewingRequest(TimestampedModel, SoftDeleteModel):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="viewing_requests")
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField()
    preferred_date = models.DateField()
    message = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=ViewingRequestStatus.choices, default=ViewingRequestStatus.PENDING)

    class Meta:
        verbose_name = _("Viewing Request")
        verbose_name_plural = _("Viewing Requests")
        ordering = ["-created_at"]
        db_table = "viewing_requests"
        indexes = [
            models.Index(fields=["listing"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Viewing #{self.id} — {self.full_name} ({self.get_status_display()})"
