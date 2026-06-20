from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from core.constants import BookingStatus, ViewingRequestStatus
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

    def convert_to_lease(self, reviewed_by, *, owner_agreement_id=None, monthly_rent=None, deposit=None):
        """Convert an APPROVED booking into a Lease, reusing Lease creation."""
        from contract.models import Lease
        from notification.services import notify

        from core.constants import NotificationType

        if self.status != BookingStatus.APPROVED:
            raise ValueError("Only approved bookings can be converted")

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

        with transaction.atomic():
            lease = Lease.objects.create(
                property=self.property,
                owner_agreement_id=agreement_id,
                tenant=self.tenant,
                start_date=self.requested_start_date,
                end_date=self.requested_end_date,
                monthly_rent=rent,
                deposit=deposit if deposit is not None else rent,
            )
            self.status = BookingStatus.CONVERTED
            self.reviewed_by = reviewed_by
            self.converted_lease = lease
            self.save(update_fields=["status", "reviewed_by", "converted_lease", "updated_at"])

        notify(
            recipient=self.tenant,
            type=NotificationType.BOOKING_STATUS,
            title=str(_("Booking confirmed")),
            body=str(_("Your booking for %(name)s has been confirmed.")) % {"name": self.property.name},
            related_object_type="booking",
            related_object_id=self.id,
        )
        return lease
