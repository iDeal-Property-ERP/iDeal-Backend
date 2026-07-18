from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import Currency, PaymentMethod, PaymentStatus, PayoutMethod, PayoutStatus
from core.models import SoftDeleteModel, TimestampedModel


class Payment(TimestampedModel, SoftDeleteModel):
    lease = models.ForeignKey("contract.Lease", on_delete=models.PROTECT, related_name="payments")
    tenant = models.ForeignKey("account.User", on_delete=models.PROTECT, related_name="payments")
    paid_by = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="recorded_payments",
        verbose_name=_("Paid By"),
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Amount"))
    currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.USD, verbose_name=_("Currency")
    )
    payment_date = models.DateField(verbose_name=_("Payment Date"))
    due_date = models.DateField(verbose_name=_("Due Date"))
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        verbose_name=_("Status"),
    )
    method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        verbose_name=_("Method"),
    )
    notes = models.TextField(null=True, blank=True, verbose_name=_("Notes"))
    # Seam for online payment gateways (Click / Payme / Uzum). The gateway
    # callback would set this reference and flip status to PAID.
    # TODO: wire gateway callback to mark the payment PAID using gateway_ref.
    gateway_ref = models.CharField(max_length=128, null=True, blank=True, verbose_name=_("Gateway Reference"))

    class Meta:
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        ordering = ["-payment_date"]
        db_table = "payments"
        indexes = [
            models.Index(fields=["lease"]),
            models.Index(fields=["tenant"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Payment #{self.id} — {self.tenant} ({self.get_status_display()})"

    def clean(self):
        from core.constants import PropertyEngagementType

        if self.lease_id and self.lease.property.engagement_type != PropertyEngagementType.MANAGED:
            raise ValidationError(_("One-off brokerage properties cannot have rent payments."))

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class ExchangeRate(TimestampedModel, SoftDeleteModel):
    currency = models.CharField(max_length=3, choices=Currency.choices, verbose_name=_("Currency"))
    rate = models.DecimalField(max_digits=15, decimal_places=4, verbose_name=_("Rate"))
    effective_date = models.DateField(verbose_name=_("Effective Date"))

    class Meta:
        verbose_name = _("Exchange Rate")
        verbose_name_plural = _("Exchange Rates")
        ordering = ["-effective_date", "-created_at"]
        db_table = "exchange_rates"

    def __str__(self):
        return f"{self.currency} = {self.rate} UZS ({self.effective_date})"


class PayoutSchedule(TimestampedModel, SoftDeleteModel):
    owner_agreement = models.ForeignKey(
        "contract.OwnerAgreement",
        on_delete=models.PROTECT,
        related_name="payout_schedules",
        verbose_name=_("Owner Agreement"),
    )
    owner = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="payout_schedules",
        verbose_name=_("Owner"),
    )
    # Links a payout accrual to the tenant payment that triggered it. The
    # OneToOne enforces one-payout-per-payment at the DB level (idempotency).
    source_payment = models.OneToOneField(
        "finance.Payment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="owner_payout",
        verbose_name=_("Source Payment"),
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Amount"))
    currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.USD, verbose_name=_("Currency")
    )
    scheduled_date = models.DateField(verbose_name=_("Scheduled Date"))
    paid_date = models.DateField(null=True, blank=True, verbose_name=_("Paid Date"))
    status = models.CharField(
        max_length=20,
        choices=PayoutStatus.choices,
        default=PayoutStatus.SCHEDULED,
        verbose_name=_("Status"),
    )
    method = models.CharField(
        max_length=20,
        choices=PayoutMethod.choices,
        default=PayoutMethod.BANK_TRANSFER,
        verbose_name=_("Method"),
    )
    # Shared reason line for the HELD and CANCELLED transitions (e.g. "bank
    # details invalid" while held, or the cancellation note).
    status_reason = models.TextField(null=True, blank=True, verbose_name=_("Status Reason"))

    class Meta:
        verbose_name = _("Payout Schedule")
        verbose_name_plural = _("Payout Schedules")
        ordering = ["-scheduled_date"]
        db_table = "payout_schedules"
        indexes = [
            models.Index(fields=["owner"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Payout #{self.id} — {self.owner} ({self.get_status_display()})"

    def clean(self):
        from core.constants import PropertyEngagementType

        if self.owner_agreement_id and self.owner_agreement.property.engagement_type != PropertyEngagementType.MANAGED:
            raise ValidationError(_("One-off brokerage properties cannot have owner payouts."))

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)
