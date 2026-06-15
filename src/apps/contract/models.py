from datetime import date

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from core.constants import LeaseStatus, OwnerAgreementStatus, PropertyStatus
from core.models import SoftDeleteModel, TimestampedModel


class OwnerAgreement(TimestampedModel, SoftDeleteModel):
    owner = models.ForeignKey("account.User", on_delete=models.PROTECT, related_name="owner_agreements")
    property = models.ForeignKey("property.Property", on_delete=models.PROTECT, related_name="owner_agreements")
    agreement_number = models.CharField(max_length=50, unique=True)
    signed_date = models.DateField()
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=OwnerAgreementStatus.choices, default=OwnerAgreementStatus.ACTIVE)
    terms = models.TextField(null=True, blank=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)

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

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_instance = type(self).objects.filter(pk=self.pk).first() if not is_new else None

        with transaction.atomic():
            super().save(*args, **kwargs)

            if is_new and self.status == LeaseStatus.ACTIVE:
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
