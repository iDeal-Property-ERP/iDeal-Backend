from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import Currency, VASOrderStatus, VASServiceType
from core.models import SoftDeleteModel, TimestampedModel


class ServiceCatalogItem(TimestampedModel, SoftDeleteModel):
    """A value-added service the platform offers (cleaning, handyman, utilities…)."""

    service_type = models.CharField(
        max_length=20,
        choices=VASServiceType.choices,
        default=VASServiceType.OTHER,
        verbose_name=_("Service Type"),
    )
    name = models.CharField(max_length=150, verbose_name=_("Name"))
    partner_name = models.CharField(max_length=150, null=True, blank=True, verbose_name=_("Partner Name"))
    description = models.TextField(null=True, blank=True, verbose_name=_("Description"))
    base_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Base Price"))
    currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.USD, verbose_name=_("Currency")
    )
    # Company commission earned from the partner (percent of cost).
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Commission Rate")
    )
    # Cashback given back to the tenant (percent of cost).
    cashback_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Cashback Rate")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Is Active"))

    class Meta:
        verbose_name = _("Service Catalog Item")
        verbose_name_plural = _("Service Catalog Items")
        ordering = ["service_type", "name"]
        db_table = "vas_catalog_items"
        indexes = [
            models.Index(fields=["service_type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_service_type_display()})"


class ServiceOrder(TimestampedModel, SoftDeleteModel):
    catalog_item = models.ForeignKey(
        ServiceCatalogItem, on_delete=models.PROTECT, related_name="orders", verbose_name=_("Catalog Item")
    )
    tenant = models.ForeignKey(
        "account.User", on_delete=models.PROTECT, related_name="service_orders", verbose_name=_("Tenant")
    )
    property = models.ForeignKey(
        "property.Property", on_delete=models.PROTECT, related_name="service_orders", verbose_name=_("Property")
    )
    lease = models.ForeignKey(
        "contract.Lease",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_orders",
        verbose_name=_("Lease"),
    )
    status = models.CharField(
        max_length=20,
        choices=VASOrderStatus.choices,
        default=VASOrderStatus.REQUESTED,
        verbose_name=_("Status"),
    )
    cost = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Cost"))
    currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.USD, verbose_name=_("Currency")
    )
    commission_earned = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Commission Earned")
    )
    cashback_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Cashback Amount")
    )
    scheduled_for = models.DateField(null=True, blank=True, verbose_name=_("Scheduled For"))
    notes = models.TextField(null=True, blank=True, verbose_name=_("Notes"))
    cancellation_reason = models.TextField(null=True, blank=True, verbose_name=_("Cancellation Reason"))
    # Stamped on the transition to COMPLETED; legacy completed rows have NULL —
    # P&L month-attribution falls back to updated_at for those.
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Completed At"))

    class Meta:
        verbose_name = _("Service Order")
        verbose_name_plural = _("Service Orders")
        ordering = ["-created_at"]
        db_table = "vas_orders"
        indexes = [
            models.Index(fields=["tenant"]),
            models.Index(fields=["property"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Order #{self.id} — {self.catalog_item.name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # Derive company commission and tenant cashback from the catalog rates.
        # Coerce via str() so float / Decimal / str inputs all work uniformly.
        cost = Decimal(str(self.cost))
        rate = Decimal(str(self.catalog_item.commission_rate or "0"))
        cashback = Decimal(str(self.catalog_item.cashback_rate or "0"))
        self.commission_earned = (cost * rate / Decimal("100")).quantize(Decimal("0.01"))
        self.cashback_amount = (cost * cashback / Decimal("100")).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
