from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.constants import LeaseStatus, OnboardingStatus, OwnerAgreementStatus, PropertyEngagementType, PropertyStatus
from core.models import SoftDeleteModel, TimestampedModel


class OwnerAgreement(TimestampedModel, SoftDeleteModel):
    previous_agreement = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="renewed_agreement",
        verbose_name=_("Previous Agreement"),
    )
    owner = models.ForeignKey("account.User", on_delete=models.PROTECT, related_name="owner_agreements")
    property = models.ForeignKey("property.Property", on_delete=models.PROTECT, related_name="owner_agreements")
    agreement_number = models.CharField(max_length=50, unique=True)
    signed_date = models.DateField()
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=OwnerAgreementStatus.choices, default=OwnerAgreementStatus.ACTIVE)
    terms = models.TextField(null=True, blank=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    # Agreement economics are the legal source of truth. Property pricing is
    # market/listing data and must never change an existing settlement.
    gross_floor_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    payout_day = models.PositiveSmallIntegerField(default=25)

    class Meta:
        verbose_name = _("Owner Agreement")
        verbose_name_plural = _("Owner Agreements")
        ordering = ["-created_at"]
        db_table = "owner_agreements"
        indexes = [
            models.Index(fields=["owner"]),
            models.Index(fields=["property"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.agreement_number} — {self.property.name}"

    def clean(self):
        if self.property_id and self.property.engagement_type != PropertyEngagementType.MANAGED:
            raise ValidationError(_("One-off brokerage properties cannot have owner agreements."))
        for field_name in ("commission_rate", "gross_floor_amount"):
            value = getattr(self, field_name)
            if value is not None:
                field = self._meta.get_field(field_name)
                setattr(self, field_name, field.to_python(value))
        if self.commission_rate is not None and not Decimal("0") <= self.commission_rate <= Decimal("100"):
            raise ValidationError(_("Commission rate must be between 0 and 100."))
        if self.payout_day and not 1 <= self.payout_day <= 31:
            raise ValidationError(_("Payout day must be between 1 and 31."))

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def renew(
        self,
        new_start_date,
        new_end_date,
        commission_rate=None,
        gross_floor_amount=None,
        currency=None,
        payout_day=None,
        agreement_number=None,
        terms=None,
    ):
        with transaction.atomic():
            if agreement_number is None:
                n = OwnerAgreement.objects.filter(agreement_number__startswith=f"{self.agreement_number}-R").count() + 1
                agreement_number = f"{self.agreement_number}-R{n}"
            new_agreement = OwnerAgreement.objects.create(
                previous_agreement=self,
                owner=self.owner,
                property=self.property,
                agreement_number=agreement_number,
                signed_date=date.today(),
                start_date=new_start_date,
                end_date=new_end_date,
                status=OwnerAgreementStatus.ACTIVE,
                terms=terms if terms is not None else self.terms,
                commission_rate=commission_rate if commission_rate is not None else self.commission_rate,
                gross_floor_amount=gross_floor_amount if gross_floor_amount is not None else self.gross_floor_amount,
                currency=currency if currency is not None else self.currency,
                payout_day=payout_day if payout_day is not None else self.payout_day,
            )
            self.status = OwnerAgreementStatus.EXPIRED
            self.save(update_fields=["status", "updated_at"])
            return new_agreement

    def terminate(self):
        self.status = OwnerAgreementStatus.TERMINATED
        self.save(update_fields=["status", "updated_at"])
        return self


class Lease(TimestampedModel, SoftDeleteModel):
    property = models.ForeignKey("property.Property", on_delete=models.PROTECT, related_name="leases")
    owner_agreement = models.ForeignKey(OwnerAgreement, on_delete=models.PROTECT, related_name="leases")
    tenant = models.ForeignKey("account.User", on_delete=models.PROTECT, related_name="leases")
    start_date = models.DateField()
    end_date = models.DateField()
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2)
    deposit = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=LeaseStatus.choices, default=LeaseStatus.ACTIVE)

    class Meta:
        verbose_name = _("Lease")
        verbose_name_plural = _("Leases")
        ordering = ["-created_at"]
        db_table = "leases"
        indexes = [
            models.Index(fields=["property"]),
            models.Index(fields=["tenant"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Lease #{self.id} — {self.property.name} ({self.get_status_display()})"

    def clean(self):
        if self.property_id and self.property.engagement_type != PropertyEngagementType.MANAGED:
            raise ValidationError(_("One-off brokerage properties cannot have leases."))

    def save(self, *args, **kwargs):
        self.clean()
        is_new = self.pk is None
        old_instance = type(self).objects.filter(pk=self.pk).first() if not is_new else None

        # Existing management/signing clients mark a lease active. A signed
        # future lease is scheduled rather than occupying inventory today.
        if (
            old_instance
            and old_instance.status == LeaseStatus.PENDING_SIGNATURE
            and self.status == LeaseStatus.ACTIVE
            and self.start_date > date.today()
        ):
            self.status = LeaseStatus.SCHEDULED

        with transaction.atomic():
            super().save(*args, **kwargs)

            if self.status == LeaseStatus.ACTIVE and (is_new or old_instance.status != LeaseStatus.ACTIVE):
                self.property.status = PropertyStatus.RENTED
                self.property.vacant_since = None
                self.property.vacant_days = 0
                self.property.save(update_fields=["status", "vacant_since", "vacant_days"])

            if (
                old_instance
                and old_instance.status != self.status
                and self.status in (LeaseStatus.EXPIRED, LeaseStatus.TERMINATED)
            ):
                self.property.status = PropertyStatus.VACANT
                self.property.vacant_since = date.today()
                self.property.vacant_days = 0
                self.property.save(update_fields=["status", "vacant_since", "vacant_days"])

    def terminate(self, end_date=None, reason=None):
        with transaction.atomic():
            self.end_date = end_date or self.end_date
            self.status = LeaseStatus.TERMINATED
            self.save()
            return self

    def renew(self, new_start_date, new_end_date, new_monthly_rent, deposit=None):
        with transaction.atomic():
            new_lease = Lease.objects.create(
                property=self.property,
                owner_agreement=self.owner_agreement,
                tenant=self.tenant,
                start_date=new_start_date,
                end_date=new_end_date,
                monthly_rent=new_monthly_rent,
                deposit=deposit or self.deposit,
            )
            self.status = LeaseStatus.RENEWED
            self.save(update_fields=["status", "updated_at"])
            LeaseRenewal.objects.create(
                previous_lease=self,
                new_lease=new_lease,
                renewal_date=date.today(),
                new_start_date=new_start_date,
                new_end_date=new_end_date,
                new_monthly_rent=new_monthly_rent,
            )
            return new_lease


class LeaseAgreementSegment(TimestampedModel, SoftDeleteModel):
    lease = models.ForeignKey(Lease, on_delete=models.PROTECT, related_name="agreement_segments")
    owner_agreement = models.ForeignKey(
        OwnerAgreement, on_delete=models.PROTECT, related_name="lease_segments"
    )
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        verbose_name = _("Lease Agreement Segment")
        verbose_name_plural = _("Lease Agreement Segments")
        ordering = ["start_date"]
        db_table = "lease_agreement_segments"
        constraints = [
            models.UniqueConstraint(
                fields=["lease", "owner_agreement", "start_date"], name="unique_lease_agreement_segment"
            )
        ]

    def __str__(self):
        return f"Lease #{self.lease_id} · Agreement #{self.owner_agreement_id}"


class PublicOffer(TimestampedModel, SoftDeleteModel):
    """Versioned public offer (oferta) an owner accepts during onboarding."""

    version = models.CharField(max_length=20, unique=True, verbose_name=_("Version"))
    body = models.TextField(verbose_name=_("Body"))
    is_active = models.BooleanField(default=True, verbose_name=_("Is Active"))

    class Meta:
        verbose_name = _("Public Offer")
        verbose_name_plural = _("Public Offers")
        ordering = ["-created_at"]
        db_table = "public_offers"

    def __str__(self):
        return f"Public Offer {self.version}"

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).order_by("-created_at").first()


class OwnerOnboarding(TimestampedModel, SoftDeleteModel):
    """An owner's self-service request to put a property under management.

    The owner submits a property (created in PENDING_REVIEW) and digitally
    accepts the public offer. Management then approves (generating an
    OwnerAgreement) or rejects.
    """

    owner = models.ForeignKey(
        "account.User", on_delete=models.PROTECT, related_name="onboardings", verbose_name=_("Owner")
    )
    property = models.ForeignKey(
        "property.Property", on_delete=models.PROTECT, related_name="onboardings", verbose_name=_("Property")
    )
    status = models.CharField(
        max_length=20,
        choices=OnboardingStatus.choices,
        default=OnboardingStatus.SUBMITTED,
        verbose_name=_("Status"),
    )
    offer_version = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("Offer Version"))
    offer_terms_snapshot = models.TextField(null=True, blank=True, verbose_name=_("Offer Terms Snapshot"))
    offer_accepted_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Offer Accepted At"))
    reviewed_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_onboardings",
        verbose_name=_("Reviewed By"),
    )
    review_notes = models.TextField(null=True, blank=True, verbose_name=_("Review Notes"))
    generated_agreement = models.ForeignKey(
        OwnerAgreement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboardings",
        verbose_name=_("Generated Agreement"),
    )

    class Meta:
        verbose_name = _("Owner Onboarding")
        verbose_name_plural = _("Owner Onboardings")
        ordering = ["-created_at"]
        db_table = "owner_onboardings"
        indexes = [
            models.Index(fields=["owner"]),
            models.Index(fields=["property"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Onboarding #{self.id} — {self.property.name} ({self.get_status_display()})"

    def clean(self):
        if self.property_id and self.property.engagement_type != PropertyEngagementType.MANAGED:
            raise ValidationError(_("One-off brokerage properties cannot enter owner onboarding."))

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def approve(self, reviewed_by, *, commission_rate, start_date, end_date, agreement_number=None, terms=None):
        """Approve the onboarding: free the property and generate an OwnerAgreement."""
        from notification.services import notify

        from core.constants import NotificationType

        with transaction.atomic():
            prop = self.property
            prop.status = PropertyStatus.VACANT
            prop.vacant_since = date.today()
            prop.vacant_days = 0
            # Saving with status in update_fields triggers the marketplace listing signal.
            prop.save(update_fields=["status", "vacant_since", "vacant_days", "updated_at"])

            agreement = OwnerAgreement.objects.create(
                owner=self.owner,
                property=prop,
                agreement_number=agreement_number or f"AG-ONB-{self.id:05d}",
                signed_date=date.today(),
                start_date=start_date,
                end_date=end_date,
                status=OwnerAgreementStatus.ACTIVE,
                terms=terms or self.offer_terms_snapshot,
                commission_rate=commission_rate,
                gross_floor_amount=prop.ask_price or Decimal("0.00"),
                currency=prop.ask_currency,
                payout_day=25,
            )
            self.status = OnboardingStatus.APPROVED
            self.reviewed_by = reviewed_by
            self.generated_agreement = agreement
            self.save(update_fields=["status", "reviewed_by", "generated_agreement", "updated_at"])

        notify(
            recipient=self.owner,
            type=NotificationType.OWNER_ONBOARDING,
            title=str(_("Property approved")),
            body=str(_("Your property %(name)s is now under management.")) % {"name": prop.name},
            related_object_type="owner_onboarding",
            related_object_id=self.id,
        )
        return agreement

    def reject(self, reviewed_by, review_notes=None):
        from notification.services import notify

        from core.constants import NotificationType

        self.status = OnboardingStatus.REJECTED
        self.reviewed_by = reviewed_by
        self.review_notes = review_notes
        self.save(update_fields=["status", "reviewed_by", "review_notes", "updated_at"])

        notify(
            recipient=self.owner,
            type=NotificationType.OWNER_ONBOARDING,
            title=str(_("Property submission declined")),
            body=review_notes or str(_("Your property submission was not approved.")),
            related_object_type="owner_onboarding",
            related_object_id=self.id,
        )

    def accept_offer(self, offer):
        self.offer_version = offer.version if offer else None
        self.offer_terms_snapshot = offer.body if offer else None
        self.offer_accepted_at = timezone.now()


class LeaseRenewal(TimestampedModel, SoftDeleteModel):
    previous_lease = models.ForeignKey(Lease, on_delete=models.PROTECT, related_name="renewals_as_previous")
    new_lease = models.ForeignKey(Lease, on_delete=models.PROTECT, related_name="renewals_as_new")
    renewal_date = models.DateField()
    new_start_date = models.DateField()
    new_end_date = models.DateField()
    new_monthly_rent = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _("Lease Renewal")
        verbose_name_plural = _("Lease Renewals")
        ordering = ["-renewal_date"]
        db_table = "lease_renewals"
        indexes = [
            models.Index(fields=["previous_lease"]),
            models.Index(fields=["new_lease"]),
        ]

    def __str__(self):
        return f"Renewal #{self.id}: Lease #{self.previous_lease_id} → #{self.new_lease_id}"
