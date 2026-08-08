from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from core.constants import (
    BrokerageCommissionType,
    Currency,
    FurnishingType,
    OneOffChannel,
    OneOffDealStatus,
    PaymentMethod,
    PropertyEngagementType,
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
    area_sqm = models.PositiveSmallIntegerField(null=True, blank=True)
    floor = models.PositiveSmallIntegerField(null=True, blank=True)
    total_floors = models.PositiveSmallIntegerField(null=True, blank=True)
    furnishing = models.CharField(max_length=20, choices=FurnishingType.choices, default=FurnishingType.UNFURNISHED)
    amenities = models.ManyToManyField(Amenity, blank=True, related_name="properties")
    owner = models.ForeignKey(
        "account.User", on_delete=models.PROTECT, related_name="owned_properties", null=True, blank=True
    )
    engagement_type = models.CharField(
        max_length=20,
        choices=PropertyEngagementType.choices,
        default=PropertyEngagementType.MANAGED,
        db_index=True,
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
            models.Index(fields=["engagement_type", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(engagement_type=PropertyEngagementType.MANAGED) | models.Q(owner__isnull=True),
                name="one_off_property_has_no_owner",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        """Keep engagement immutable once a property becomes commercially active."""
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).values("engagement_type", "status").first()
            if old and old["engagement_type"] != self.engagement_type:
                has_history = (
                    old["status"] != PropertyStatus.DRAFT
                    or OneOffDeal.objects.filter(property_id=self.pk).exists()
                    or self.owner_agreements.exists()
                    or self.leases.exists()
                )
                if has_history:
                    raise ValidationError(_("A property's engagement type cannot change after activation."))
        if self.engagement_type == PropertyEngagementType.ONE_OFF and self.owner_id is not None:
            raise ValidationError(_("One-off brokerage properties cannot have an owner account."))
        return super().save(*args, **kwargs)


class OneOffDeal(TimestampedModel, SoftDeleteModel):
    """Staff-operated brokerage deal with contact snapshots, never portal users."""

    property = models.OneToOneField(Property, on_delete=models.PROTECT, related_name="one_off_deal")
    seller_name = models.CharField(max_length=150)
    seller_phone = models.CharField(max_length=30)
    seller_email = models.EmailField(null=True, blank=True)
    renter_name = models.CharField(max_length=150, null=True, blank=True)
    renter_phone = models.CharField(max_length=30, null=True, blank=True)
    renter_email = models.EmailField(null=True, blank=True)
    channel = models.CharField(max_length=20, choices=OneOffChannel.choices)
    status = models.CharField(
        max_length=20,
        choices=OneOffDealStatus.choices,
        default=OneOffDealStatus.DRAFT,
        db_index=True,
    )
    commission_type = models.CharField(
        max_length=20,
        choices=BrokerageCommissionType.choices,
        default=BrokerageCommissionType.NONE,
    )
    commission_fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    commission_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    commission_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    agreed_monthly_rent = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    agreed_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    close_date = models.DateField(null=True, blank=True)
    close_notes = models.TextField(blank=True, default="")
    evidence = models.JSONField(default=list, blank=True)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    commission_uzs_amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    commission_conversion_rate = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    closed_by = models.ForeignKey(
        "account.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="closed_one_off_deals"
    )

    class Meta:
        verbose_name = _("One-off brokerage deal")
        verbose_name_plural = _("One-off brokerage deals")
        ordering = ["-created_at"]
        db_table = "one_off_deals"
        indexes = [models.Index(fields=["status"]), models.Index(fields=["channel", "status"])]

    def clean(self):
        if self.property_id and self.property.engagement_type != PropertyEngagementType.ONE_OFF:
            raise ValidationError(_("A one-off deal requires a one-off brokerage property."))
        # Drafts intentionally accept incomplete terms for autosave. The complete
        # commercial validation runs again at activation and close.
        if self.status == OneOffDealStatus.DRAFT:
            return
        if self.commission_type == BrokerageCommissionType.NONE:
            if self.commission_fixed_amount or self.commission_percentage:
                raise ValidationError(_("No-fee deals cannot carry commission terms."))
        elif self.commission_type == BrokerageCommissionType.FIXED:
            if not self.commission_fixed_amount or self.commission_fixed_amount <= 0 or self.commission_percentage:
                raise ValidationError(_("A fixed-fee deal requires one positive fixed amount."))
        elif self.commission_type == BrokerageCommissionType.PERCENTAGE:
            if not self.commission_percentage or not Decimal("0") < self.commission_percentage <= Decimal("100"):
                raise ValidationError(_("A percentage commission must be greater than 0 and at most 100."))
            if self.commission_fixed_amount:
                raise ValidationError(_("A percentage-fee deal cannot carry a fixed amount."))

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def _activation_missing(self):
        """Return human-readable readiness gaps without imposing managed fields."""
        prop = self.property
        missing = []
        for field in ("name", "address", "district_id", "rooms", "area_sqm", "floor", "total_floors", "ask_price"):
            value = getattr(prop, field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field.removesuffix("_id"))
        if not self.seller_name.strip() or not self.seller_phone.strip():
            missing.append("seller")
        if self.channel not in OneOffChannel.values():
            missing.append("channel")
        invalid_commission = (
            (self.commission_type == BrokerageCommissionType.NONE and (self.commission_fixed_amount or self.commission_percentage))
            or (
                self.commission_type == BrokerageCommissionType.FIXED
                and (not self.commission_fixed_amount or self.commission_fixed_amount <= 0 or self.commission_percentage)
            )
            or (
                self.commission_type == BrokerageCommissionType.PERCENTAGE
                and (
                    not self.commission_percentage
                    or not Decimal("0") < self.commission_percentage <= Decimal("100")
                    or self.commission_fixed_amount
                )
            )
            or self.commission_type not in BrokerageCommissionType.values()
        )
        if invalid_commission:
            missing.append("commission")
        if self.channel == OneOffChannel.MARKETPLACE and prop.photos.count() < 5:
            missing.append("photos")
        return missing

    def _depublish(self):
        from marketplace.models import Listing

        Listing.objects.filter(property=self.property).update(is_active=False, status="archived")

    def activate(self):
        if self.status not in (OneOffDealStatus.DRAFT, OneOffDealStatus.PAUSED):
            raise ValidationError(_("Only draft or paused deals can be activated."))
        missing = self._activation_missing()
        if missing:
            raise ValidationError(_("One-off deal is not ready: %(missing)s") % {"missing": ", ".join(missing)})
        with transaction.atomic():
            self.status = OneOffDealStatus.ACTIVE
            self.save(update_fields=["status", "updated_at"])
            self.property.status = PropertyStatus.VACANT
            self.property.vacant_since = None
            self.property.vacant_days = 0
            self.property.save(update_fields=["status", "vacant_since", "vacant_days", "updated_at"])
        return self

    def pause(self):
        if self.status != OneOffDealStatus.ACTIVE:
            raise ValidationError(_("Only active deals can be paused."))
        self.status = OneOffDealStatus.PAUSED
        self.save(update_fields=["status", "updated_at"])
        self._depublish()
        return self

    def close_won(self, *, renter_name, renter_phone, renter_email, agreed_monthly_rent, agreed_currency, close_date, notes, evidence, closed_by, keep_property_active=False):
        from finance.utils import convert_amount

        if self.status not in (OneOffDealStatus.ACTIVE, OneOffDealStatus.PAUSED):
            raise ValidationError(_("Only active or paused deals can be closed."))
        if not renter_name or not renter_phone or not agreed_monthly_rent or agreed_monthly_rent <= 0:
            raise ValidationError(_("A renter contact and positive agreed monthly rent are required to close a deal."))
        if self.commission_type == BrokerageCommissionType.NONE:
            commission = Decimal("0.00")
        elif self.commission_type == BrokerageCommissionType.FIXED:
            commission = self.commission_fixed_amount
        else:
            if agreed_currency != self.commission_currency:
                raise ValidationError(_("Percentage commission must use the agreed rent currency."))
            commission = (agreed_monthly_rent * self.commission_percentage / Decimal("100")).quantize(Decimal("0.01"))
        if commission == 0:
            uzs_amount = Decimal("0.00")
            rate = Decimal("1.000000")
        else:
            try:
                uzs_amount = convert_amount(commission, self.commission_currency, Currency.UZS)
            except ValueError:
                # Commercial closure must not depend on the reporting-rate table.
                # Keep the original-currency commission immutable and leave the
                # UZS snapshot pending until Finance supplies a valid rate.
                uzs_amount = None
                rate = None
            else:
                rate = (uzs_amount / commission).quantize(Decimal("0.000001"))
        with transaction.atomic():
            self.renter_name = renter_name
            self.renter_phone = renter_phone
            self.renter_email = renter_email or None
            self.agreed_monthly_rent = agreed_monthly_rent
            self.agreed_currency = agreed_currency
            self.close_date = close_date
            self.close_notes = notes or ""
            self.evidence = evidence or []
            self.commission_amount = commission
            self.commission_uzs_amount = uzs_amount
            self.commission_conversion_rate = rate
            self.closed_by = closed_by
            self.status = OneOffDealStatus.CLOSED_WON
            self.save()
            if not keep_property_active:
                self.property.status = PropertyStatus.ARCHIVED
                self.property.save(update_fields=["status", "updated_at"])
                self._depublish()
        return self

    def close_lost(self, *, close_date, notes, evidence, closed_by, keep_property_active=False):
        if self.status not in (OneOffDealStatus.ACTIVE, OneOffDealStatus.PAUSED):
            raise ValidationError(_("Only active or paused deals can be closed."))
        with transaction.atomic():
            self.close_date = close_date
            self.close_notes = notes or ""
            self.evidence = evidence or []
            self.closed_by = closed_by
            self.status = OneOffDealStatus.CLOSED_LOST
            self.save()
            if not keep_property_active:
                self.property.status = PropertyStatus.ARCHIVED
                self.property.save(update_fields=["status", "updated_at"])
                self._depublish()
        return self

    def archive(self):
        if self.status not in (OneOffDealStatus.CLOSED_WON, OneOffDealStatus.CLOSED_LOST):
            raise ValidationError(_("Only closed deals can be archived."))
        self.status = OneOffDealStatus.ARCHIVED
        self.save(update_fields=["status", "updated_at"])
        return self


class OneOffCommissionReceipt(TimestampedModel):
    """The single full collection for a closed one-off commission."""

    deal = models.OneToOneField(OneOffDeal, on_delete=models.PROTECT, related_name="receipt")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    received_date = models.DateField()
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    reference = models.CharField(max_length=128, blank=True, default="")
    recorded_by = models.ForeignKey(
        "account.User", on_delete=models.PROTECT, related_name="recorded_one_off_receipts"
    )

    class Meta:
        verbose_name = _("One-off commission receipt")
        verbose_name_plural = _("One-off commission receipts")
        ordering = ["-received_date", "-created_at"]
        db_table = "one_off_commission_receipts"

    def clean(self):
        if self.deal.status not in (OneOffDealStatus.CLOSED_WON, OneOffDealStatus.ARCHIVED):
            raise ValidationError(_("Only a closed-won deal can receive a commission receipt."))
        if self.deal.commission_amount is None:
            raise ValidationError(_("The deal commission has not been calculated."))
        if self.amount != self.deal.commission_amount or self.currency != self.deal.commission_currency:
            raise ValidationError(_("The v1 receipt must collect the full calculated commission exactly once."))

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class OneOffCommissionReceiptAttachment(TimestampedModel):
    """A staff-only source document supporting a received brokerage commission."""

    receipt = models.ForeignKey(
        OneOffCommissionReceipt,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to="one_off_brokerage/receipts/")
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True, default="")
    size_bytes = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("One-off commission receipt attachment")
        verbose_name_plural = _("One-off commission receipt attachments")
        ordering = ["created_at"]
        db_table = "one_off_commission_receipt_attachments"


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
