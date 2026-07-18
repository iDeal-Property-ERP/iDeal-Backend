from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from core.constants import (
    BookingStatus,
    ContactInquiryStatus,
    ListingStatus,
    MinimumStay,
    ViewingRequestStatus,
    ViewingTimeSlot,
)
from core.models import SoftDeleteModel, TimestampedModel


class LeaseConflictError(Exception):
    """Raised when converting a booking whose property already has an active lease."""


class Listing(TimestampedModel, SoftDeleteModel):
    property = models.OneToOneField("property.Property", on_delete=models.CASCADE, related_name="listing")
    owner_agreement = models.ForeignKey(
        "contract.OwnerAgreement", on_delete=models.SET_NULL, null=True, blank=True, related_name="listings"
    )
    status = models.CharField(max_length=20, choices=ListingStatus.choices, default=ListingStatus.PUBLISHED)
    # Kept mirrored from ``status`` (is_active == status == PUBLISHED) for back-compat with the
    # public query and the auto-listing signal.
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    description = models.TextField(null=True, blank=True)
    # ``listed_price`` is kept as a compat alias of ``monthly_price``.
    listed_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    monthly_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    # Pricing extras surfaced on the List-Your-Property wizard (step 3).
    minimum_stay = models.PositiveSmallIntegerField(choices=MinimumStay.choices(), null=True, blank=True)
    price_includes = models.JSONField(default=list, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Listing")
        verbose_name_plural = _("Listings")
        ordering = ["-is_featured", "-created_at"]
        db_table = "listings"
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_featured"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Listing #{self.id} — {self.property.name}"


class ViewingRequest(TimestampedModel, SoftDeleteModel):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="viewing_requests")
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(null=True, blank=True)
    preferred_date = models.DateField()
    preferred_time = models.CharField(max_length=10, choices=ViewingTimeSlot.choices, null=True, blank=True)
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


class ContactInquiry(TimestampedModel, SoftDeleteModel):
    """A general "Message iDeal" inquiry from the public marketplace, kept separate from
    ViewingRequest so management's viewing queue stays clean."""

    listing = models.ForeignKey(Listing, on_delete=models.SET_NULL, null=True, blank=True, related_name="inquiries")
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(null=True, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=ContactInquiryStatus.choices, default=ContactInquiryStatus.NEW)

    class Meta:
        verbose_name = _("Contact Inquiry")
        verbose_name_plural = _("Contact Inquiries")
        ordering = ["-created_at"]
        db_table = "contact_inquiries"
        indexes = [
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Inquiry #{self.id} — {self.full_name} ({self.get_status_display()})"


class FaqItem(TimestampedModel):
    """Editable FAQ entry shown on the public "How it works" page."""

    question = models.CharField(max_length=255)
    answer = models.TextField()
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("FAQ Item")
        verbose_name_plural = _("FAQ Items")
        ordering = ["sort_order", "id"]
        db_table = "faq_items"

    def __str__(self):
        return self.question


class Booking(TimestampedModel, SoftDeleteModel):
    """A logged-in tenant's reservation request against a listing (Smart Match).

    Management approves a booking and converts it into a Lease (reusing the
    existing lease-creation logic, which frees/occupies the property).
    """

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="bookings", verbose_name=_("Listing"))
    property = models.ForeignKey(
        "property.Property", on_delete=models.PROTECT, related_name="bookings", verbose_name=_("Property")
    )
    tenant = models.ForeignKey(
        "account.User", on_delete=models.PROTECT, related_name="bookings", verbose_name=_("Tenant")
    )
    requested_start_date = models.DateField(verbose_name=_("Requested Start Date"))
    requested_end_date = models.DateField(verbose_name=_("Requested End Date"))
    monthly_rent_offer = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("Monthly Rent Offer")
    )
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.REQUESTED,
        verbose_name=_("Status"),
    )
    message = models.TextField(null=True, blank=True, verbose_name=_("Message"))
    reviewed_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_bookings",
        verbose_name=_("Reviewed By"),
    )
    converted_lease = models.ForeignKey(
        "contract.Lease",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_bookings",
        verbose_name=_("Converted Lease"),
    )

    class Meta:
        verbose_name = _("Booking")
        verbose_name_plural = _("Bookings")
        ordering = ["-created_at"]
        db_table = "bookings"
        indexes = [
            models.Index(fields=["listing"]),
            models.Index(fields=["tenant"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Booking #{self.id} — {self.tenant} ({self.get_status_display()})"

    def clean(self):
        from core.constants import PropertyEngagementType

        if self.property.engagement_type == PropertyEngagementType.ONE_OFF:
            raise ValidationError(_("One-off marketplace properties accept contact leads, not tenant bookings."))

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def convert_to_lease(
        self,
        reviewed_by,
        *,
        owner_agreement_id=None,
        monthly_rent=None,
        deposit=None,
        start_date=None,
        end_date=None,
    ):
        """Convert an APPROVED booking into a Lease, reusing Lease creation.

        Also raises a pending deposit invoice and notifies the tenant to sign
        and pay (Booking → Lease → Payment flow). Raises ``LeaseConflictError``
        if the property already carries an active lease.
        """
        from contract.models import Lease
        from finance.models import Payment
        from notification.services import notify

        from core.constants import LeaseStatus, NotificationType, PaymentStatus, PropertyEngagementType

        if self.property.engagement_type == PropertyEngagementType.ONE_OFF:
            raise ValueError("One-off brokerage properties cannot create leases")
        if self.status != BookingStatus.APPROVED:
            raise ValueError("Only approved bookings can be converted")

        if self.property.leases.filter(status=LeaseStatus.ACTIVE).exists():
            raise LeaseConflictError("This property already has an active lease")

        from core.constants import OwnerAgreementStatus

        agreement_id = owner_agreement_id or (self.listing.owner_agreement_id if self.listing else None)
        if agreement_id is None:
            # Fall back to the property's active owner agreement.
            active = (
                self.property.owner_agreements.filter(status=OwnerAgreementStatus.ACTIVE)
                .order_by("-created_at")
                .first()
            )
            agreement_id = active.id if active else None
        if agreement_id is None:
            raise ValueError("An owner agreement is required to create a lease")

        rent = monthly_rent or self.monthly_rent_offer or self.listing.listed_price or self.property.tenant_charge_price
        deposit_amount = deposit if deposit is not None else rent
        lease_start = start_date or self.requested_start_date
        lease_end = end_date or self.requested_end_date

        with transaction.atomic():
            lease = Lease.objects.create(
                property=self.property,
                owner_agreement_id=agreement_id,
                tenant=self.tenant,
                start_date=lease_start,
                end_date=lease_end,
                monthly_rent=rent,
                deposit=deposit_amount,
            )
            # Raise the first (deposit) invoice as PENDING — the tenant is
            # invited to sign and pay it. Stays PENDING until management/gateway
            # confirms, matching the tenant pay-now flow.
            Payment.objects.create(
                lease=lease,
                tenant=self.tenant,
                paid_by=self.tenant,
                amount=deposit_amount,
                currency=self.property.tenant_charge_currency,
                payment_date=lease_start,
                due_date=lease_start,
                status=PaymentStatus.PENDING,
                notes=str(_("Deposit")),
            )
            self.status = BookingStatus.CONVERTED
            self.reviewed_by = reviewed_by
            self.converted_lease = lease
            self.save(update_fields=["status", "reviewed_by", "converted_lease", "updated_at"])

        notify(
            recipient=self.tenant,
            type=NotificationType.BOOKING_STATUS,
            title=str(_("Booking confirmed")),
            body=str(_("Your booking for %(name)s is confirmed — please sign and pay the deposit."))
            % {"name": self.property.name},
            related_object_type="booking",
            related_object_id=self.id,
        )
        return lease
