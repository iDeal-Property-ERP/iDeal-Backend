from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import (
    FurnishingType,
    PropertyStatus,
    PropertyType,
    TariffChoices,
    VerificationVisitStatus,
)
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


class Amenity(TimestampedModel):
    """Lookup of property amenities — single source of truth for the wizard chip-set
    and the listing-detail labelled grid."""

    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Amenity")
        verbose_name_plural = _("Amenities")
        ordering = ["sort_order", "name"]
        db_table = "amenities"

    def __str__(self):
        return self.name


class Property(TimestampedModel, SoftDeleteModel):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255, blank=True, default="")
    # Publish-required fields are nullable so a DRAFT can be saved partially;
    # the publish transition enforces completeness before going VACANT.
    district = models.ForeignKey(District, on_delete=models.PROTECT, related_name="properties", null=True, blank=True)
    property_type = models.CharField(max_length=20, choices=PropertyType.choices, default=PropertyType.APARTMENT)
    rooms = models.PositiveSmallIntegerField(null=True, blank=True)
    bathrooms = models.PositiveSmallIntegerField(default=1)
    area_sqm = models.PositiveSmallIntegerField(null=True, blank=True)
    floor = models.PositiveSmallIntegerField(null=True, blank=True)
    total_floors = models.PositiveSmallIntegerField(null=True, blank=True)
    furnishing = models.CharField(max_length=20, choices=FurnishingType.choices, default=FurnishingType.UNFURNISHED)
    amenities = models.ManyToManyField(Amenity, blank=True, related_name="properties")
    owner = models.ForeignKey(
        "account.User", on_delete=models.PROTECT, related_name="owned_properties", null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=PropertyStatus.choices, default=PropertyStatus.VACANT)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_properties",
    )
    score = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    review_count = models.PositiveIntegerField(_("Review count"), default=0)
    map_lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    map_lon = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    tariff = models.CharField(max_length=20, choices=TariffChoices.choices, default=TariffChoices.STANDARD)

    ask_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    ask_currency = models.CharField(max_length=3, default="USD")
    owner_guaranteed_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    owner_guaranteed_currency = models.CharField(max_length=3, default="USD")
    tenant_charge_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tenant_charge_currency = models.CharField(max_length=3, default="USD")

    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    deposit_currency = models.CharField(max_length=3, default="USD")

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
    caption = models.CharField(_("Caption"), max_length=120, blank=True, default="")
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = _("Property Photo")
        verbose_name_plural = _("Property Photos")
        ordering = ["sort_order", "-is_primary"]
        db_table = "property_photos"

    def __str__(self):
        return f"Photo {self.id} for {self.property.name}"


class VerificationVisit(TimestampedModel):
    """A management on-site verification visit scheduled when a property is
    published. Backs the "Save & schedule verification" action and the publish
    checklist's verification row."""

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="verification_visits")
    scheduled_for = models.DateTimeField(_("Scheduled for"))
    status = models.CharField(
        max_length=20,
        choices=VerificationVisitStatus.choices,
        default=VerificationVisitStatus.SCHEDULED,
    )
    scheduled_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_verification_visits",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = _("Verification Visit")
        verbose_name_plural = _("Verification Visits")
        ordering = ["-scheduled_for"]
        db_table = "verification_visits"

    def __str__(self):
        return f"Verification visit for {self.property.name} ({self.get_status_display()})"
