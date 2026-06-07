from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import PropertyStatus, TariffChoices
from core.models import SoftDeleteModel, TimestampedModel


class District(TimestampedModel, SoftDeleteModel):
    name = models.CharField(max_length=100, unique=True)
    city = models.CharField(max_length=100, default="Toshkent")

    class Meta:
        verbose_name = _("District")
        verbose_name_plural = _("Districts")
        ordering = ["name"]
        db_table = "districts"

    def __str__(self):
        return f"{self.name}, {self.city}"


class Property(TimestampedModel, SoftDeleteModel):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255)
    district = models.ForeignKey(District, on_delete=models.PROTECT, related_name="properties")
    rooms = models.PositiveSmallIntegerField()
    area_sqm = models.PositiveSmallIntegerField()
    floor = models.PositiveSmallIntegerField()
    total_floors = models.PositiveSmallIntegerField(null=True, blank=True)
    owner = models.ForeignKey("account.User", on_delete=models.PROTECT, related_name="owned_properties")
    status = models.CharField(max_length=20, choices=PropertyStatus.choices, default=PropertyStatus.VACANT)
    score = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    map_lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    map_lon = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    tariff = models.CharField(max_length=20, choices=TariffChoices.choices, default=TariffChoices.STANDARD)

    ask_price = models.DecimalField(max_digits=12, decimal_places=2)
    ask_currency = models.CharField(max_length=3, default="USD")
    owner_guaranteed_price = models.DecimalField(max_digits=12, decimal_places=2)
    owner_guaranteed_currency = models.CharField(max_length=3, default="USD")
    tenant_charge_price = models.DecimalField(max_digits=12, decimal_places=2)
    tenant_charge_currency = models.CharField(max_length=3, default="USD")

    vacant_since = models.DateField(null=True, blank=True)
    vacant_days = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = _("Property")
        verbose_name_plural = _("Properties")
        ordering = ["-created_at"]
        db_table = "properties"
        indexes = [
            models.Index(fields=["district"]),
            models.Index(fields=["owner"]),
            models.Index(fields=["status"]),
            models.Index(fields=["map_lat", "map_lon"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class PropertyPhoto(TimestampedModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="properties/photos/")
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = _("Property Photo")
        verbose_name_plural = _("Property Photos")
        ordering = ["sort_order", "-is_primary"]
        db_table = "property_photos"

    def __str__(self):
        return f"Photo {self.id} for {self.property.name}"
