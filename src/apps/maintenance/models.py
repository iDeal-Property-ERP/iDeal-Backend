from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import CostBearer, ServiceRequestPriority, ServiceRequestStatus
from core.models import SoftDeleteModel, TimestampedModel


class ServiceRequest(TimestampedModel, SoftDeleteModel):
    property = models.ForeignKey(
        "property.Property", on_delete=models.PROTECT, related_name="service_requests", verbose_name=_("Property")
    )
    tenant = models.ForeignKey(
        "account.User", on_delete=models.PROTECT, related_name="service_requests", verbose_name=_("Tenant")
    )
    assigned_to = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_requests",
        verbose_name=_("Assigned To"),
    )
    title = models.CharField(max_length=200, verbose_name=_("Title"))
    description = models.TextField(verbose_name=_("Description"))
    priority = models.CharField(
        max_length=20,
        choices=ServiceRequestPriority.choices,
        default=ServiceRequestPriority.MEDIUM,
        verbose_name=_("Priority"),
    )
    status = models.CharField(
        max_length=20,
        choices=ServiceRequestStatus.choices,
        default=ServiceRequestStatus.OPEN,
        verbose_name=_("Status"),
    )
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("Cost"))
    cost_bearer = models.CharField(
        max_length=20,
        choices=CostBearer.choices,
        null=True,
        blank=True,
        verbose_name=_("Cost Bearer"),
    )
    resolution_notes = models.TextField(null=True, blank=True, verbose_name=_("Resolution Notes"))
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Resolved At"))

    class Meta:
        verbose_name = _("Service Request")
        verbose_name_plural = _("Service Requests")
        ordering = ["-created_at"]
        db_table = "service_requests"
        indexes = [
            models.Index(fields=["property"]),
            models.Index(fields=["tenant"]),
            models.Index(fields=["status"]),
            models.Index(fields=["assigned_to"]),
        ]

    def __str__(self):
        return f"Request #{self.id} — {self.title} ({self.get_status_display()})"


class ServiceRequestPhoto(TimestampedModel, SoftDeleteModel):
    service_request = models.ForeignKey(
        ServiceRequest, on_delete=models.CASCADE, related_name="photos", verbose_name=_("Service Request")
    )
    image = models.ImageField(upload_to="service_requests/", verbose_name=_("Image"))

    class Meta:
        verbose_name = _("Service Request Photo")
        verbose_name_plural = _("Service Request Photos")
        ordering = ["-created_at"]
        db_table = "service_request_photos"

    def __str__(self):
        return f"Photo #{self.id} for Request #{self.service_request_id}"


class ServiceRequestComment(TimestampedModel, SoftDeleteModel):
    """An internal management/technician note on a service request.

    Distinct from ``resolution_notes`` (a single post-resolution field): comments
    form the running progress thread shown in the maintenance record panel.
    """

    service_request = models.ForeignKey(
        ServiceRequest, on_delete=models.CASCADE, related_name="comments", verbose_name=_("Service Request")
    )
    author = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_request_comments",
        verbose_name=_("Author"),
    )
    body = models.TextField(verbose_name=_("Body"))

    class Meta:
        verbose_name = _("Service Request Comment")
        verbose_name_plural = _("Service Request Comments")
        ordering = ["created_at"]
        db_table = "service_request_comments"
        indexes = [
            models.Index(fields=["service_request"]),
        ]

    def __str__(self):
        return f"Comment #{self.id} on Request #{self.service_request_id}"
