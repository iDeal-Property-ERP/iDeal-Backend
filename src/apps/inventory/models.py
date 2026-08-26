from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import ConditionRating, InventoryActStatus, InventoryActType
from core.models import SoftDeleteModel, TimestampedModel


class InventoryAct(TimestampedModel, SoftDeleteModel):
    """Digital passportization: a structured condition record (Akt) for a property."""

    property = models.ForeignKey(
        "property.Property",
        on_delete=models.PROTECT,
        related_name="inventory_acts",
        verbose_name=_("Property"),
    )
    lease = models.ForeignKey(
        "contract.Lease",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_acts",
        verbose_name=_("Lease"),
    )
    act_type = models.CharField(
        max_length=20,
        choices=InventoryActType.choices,
        default=InventoryActType.GENERAL,
        verbose_name=_("Act Type"),
    )
    status = models.CharField(
        max_length=20,
        choices=InventoryActStatus.choices,
        default=InventoryActStatus.FINALIZED,
        verbose_name=_("Status"),
    )
    created_by = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="created_inventory_acts",
        verbose_name=_("Created By"),
    )
    notes = models.TextField(null=True, blank=True, verbose_name=_("Notes"))
    finalized_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Finalized At"))
    # Digital acknowledgment by the counterparty (tenant / owner). The hardware
    # E-IMZO / 360-camera flow plugs in here later.
    # TODO: integrate E-IMZO signing and 360-camera capture.
    acknowledged_by_name = models.CharField(
        max_length=200, null=True, blank=True, verbose_name=_("Acknowledged By Name")
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Acknowledged At"))
    acknowledgment_note = models.TextField(null=True, blank=True, verbose_name=_("Acknowledgment Note"))

    class Meta:
        verbose_name = _("Inventory Act")
        verbose_name_plural = _("Inventory Acts")
        ordering = ["-created_at"]
        db_table = "inventory_acts"
        indexes = [
            models.Index(fields=["property"]),
            models.Index(fields=["lease"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Act #{self.id} — {self.property.name} ({self.get_status_display()})"


class InventoryActItem(TimestampedModel, SoftDeleteModel):
    act = models.ForeignKey(InventoryAct, on_delete=models.CASCADE, related_name="items", verbose_name=_("Act"))
    area = models.CharField(max_length=120, verbose_name=_("Area"))
    condition = models.CharField(
        max_length=20,
        choices=ConditionRating.choices,
        default=ConditionRating.GOOD,
        verbose_name=_("Condition"),
    )
    notes = models.TextField(null=True, blank=True, verbose_name=_("Notes"))
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name=_("Sort Order"))

    class Meta:
        verbose_name = _("Inventory Act Item")
        verbose_name_plural = _("Inventory Act Items")
        ordering = ["sort_order", "id"]
        db_table = "inventory_act_items"
        indexes = [models.Index(fields=["act"])]

    def __str__(self):
        return f"{self.area} ({self.get_condition_display()})"


class InventoryActPhoto(TimestampedModel, SoftDeleteModel):
    act = models.ForeignKey(InventoryAct, on_delete=models.CASCADE, related_name="photos", verbose_name=_("Act"))
    item = models.ForeignKey(
        InventoryActItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="photos",
        verbose_name=_("Item"),
    )
    image = models.ImageField(upload_to="inventory_acts/", verbose_name=_("Image"))
    caption = models.CharField(max_length=200, null=True, blank=True, verbose_name=_("Caption"))

    class Meta:
        verbose_name = _("Inventory Act Photo")
        verbose_name_plural = _("Inventory Act Photos")
        ordering = ["-created_at"]
        db_table = "inventory_act_photos"
        indexes = [models.Index(fields=["act"])]

    def __str__(self):
        return f"Photo #{self.id} for Act #{self.act_id}"
