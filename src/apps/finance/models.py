from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import Currency, PaymentKind, PaymentMethod, PaymentStatus, PayoutKind, PayoutMethod, PayoutStatus
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
    rental_period = models.DateField(null=True, blank=True, verbose_name=_("Rental Period"))
    kind = models.CharField(max_length=20, choices=PaymentKind.choices, default=PaymentKind.RENT)
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
        if self.kind == PaymentKind.RENT and self.lease_id:
            agreement = self.lease.owner_agreement
            if self.currency != agreement.currency:
                raise ValidationError(_("Rent payment currency must match the owner agreement currency."))

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
    settlement = models.ForeignKey(
        "finance.OwnerSettlement",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payouts",
        verbose_name=_("Settlement"),
    )
    kind = models.CharField(max_length=30, choices=PayoutKind.choices, default=PayoutKind.BASE)
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


class OwnerSettlement(TimestampedModel, SoftDeleteModel):
    """Immutable monthly contract snapshot and its transparent calculation."""

    owner_agreement = models.ForeignKey("contract.OwnerAgreement", on_delete=models.PROTECT, related_name="settlements")
    owner = models.ForeignKey("account.User", on_delete=models.PROTECT, related_name="owner_settlements")
    period_start = models.DateField()
    period_end = models.DateField()
    covered_days = models.PositiveSmallIntegerField()
    days_in_month = models.PositiveSmallIntegerField()
    gross_floor_amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    rent_received_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    settlement_base_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    owner_payout_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ideal_cash_exposure = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = "owner_settlements"
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(fields=["owner_agreement", "period_start"], name="unique_agreement_month")
        ]
        indexes = [models.Index(fields=["owner", "period_start"])]

    def __str__(self):
        return f"Settlement {self.owner_agreement_id} · {self.period_start:%Y-%m}"


class RentReceiptAllocation(TimestampedModel):
    """Append-only allocation of paid rent to one agreement month."""

    payment = models.ForeignKey("finance.Payment", on_delete=models.PROTECT, related_name="settlement_allocations")
    settlement = models.ForeignKey(OwnerSettlement, on_delete=models.PROTECT, related_name="receipt_allocations")
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "rent_receipt_allocations"
        constraints = [
            models.UniqueConstraint(fields=["payment", "settlement"], name="unique_payment_settlement_allocation")
        ]
