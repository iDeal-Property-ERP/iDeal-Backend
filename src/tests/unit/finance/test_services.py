from datetime import date
from decimal import Decimal

import pytest
from finance.models import OwnerSettlement, PayoutSchedule
from finance.services import allocate_paid_rent, ensure_monthly_settlements

from core.constants import Currency, PaymentKind, PaymentStatus, PayoutKind, PayoutStatus
from tests.factories import OwnerAgreementFactory, PaymentFactory


@pytest.mark.django_db
class TestOwnerSettlement:
    def test_creates_vacancy_floor_and_base_payout(self):
        agreement = OwnerAgreementFactory(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            gross_floor_amount=Decimal("500.00"),
            commission_rate=Decimal("20.00"),
        )
        assert ensure_monthly_settlements(date(2026, 6, 30)) == 1
        settlement = OwnerSettlement.objects.get(owner_agreement=agreement)
        assert settlement.rent_received_amount == Decimal("0.00")
        assert settlement.owner_payout_amount == Decimal("400.00")
        assert settlement.ideal_cash_exposure == Decimal("400.00")
        assert settlement.payouts.get(kind=PayoutKind.BASE).amount == Decimal("400.00")

    def test_splits_above_floor_cash(self):
        agreement = OwnerAgreementFactory(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            gross_floor_amount=Decimal("500.00"),
            commission_rate=Decimal("20.00"),
        )
        payment = PaymentFactory(
            lease__owner_agreement=agreement,
            amount=Decimal("700.00"),
            currency=Currency.USD,
            payment_date=date(2026, 6, 10),
            due_date=date(2026, 6, 1),
            rental_period=date(2026, 6, 1),
            status=PaymentStatus.PAID,
        )
        settlement = allocate_paid_rent(payment)
        assert settlement is not None
        assert settlement.settlement_base_amount == Decimal("700.00")
        assert settlement.commission_amount == Decimal("140.00")
        assert settlement.owner_payout_amount == Decimal("560.00")
        assert settlement.ideal_cash_exposure == Decimal("0.00")

    def test_partial_cash_keeps_floor_and_records_only_uncovered_exposure(self):
        agreement = OwnerAgreementFactory(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            gross_floor_amount=Decimal("500.00"),
            commission_rate=Decimal("20.00"),
        )
        payment = PaymentFactory(
            lease__owner_agreement=agreement,
            amount=Decimal("300.00"),
            currency=Currency.USD,
            payment_date=date(2026, 6, 10),
            due_date=date(2026, 6, 1),
            rental_period=date(2026, 6, 1),
            status=PaymentStatus.PAID,
        )

        settlement = allocate_paid_rent(payment)

        assert settlement.settlement_base_amount == Decimal("500.00")
        assert settlement.owner_payout_amount == Decimal("400.00")
        assert settlement.ideal_cash_exposure == Decimal("100.00")

    def test_deposit_never_affects_settlement(self):
        agreement = OwnerAgreementFactory(
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 30), gross_floor_amount=Decimal("500.00")
        )
        deposit = PaymentFactory(
            lease__owner_agreement=agreement,
            amount=Decimal("900.00"),
            kind=PaymentKind.DEPOSIT,
            payment_date=date(2026, 6, 10),
            due_date=date(2026, 6, 1),
            rental_period=date(2026, 6, 1),
            status=PaymentStatus.PAID,
        )

        assert allocate_paid_rent(deposit) is None
        assert not OwnerSettlement.objects.filter(owner_agreement=agreement).exists()

    def test_late_cash_after_paid_base_creates_upside_adjustment(self):
        agreement = OwnerAgreementFactory(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            gross_floor_amount=Decimal("500.00"),
            commission_rate=Decimal("20.00"),
        )
        ensure_monthly_settlements(date(2026, 6, 30))
        base = PayoutSchedule.objects.get(owner_agreement=agreement, kind=PayoutKind.BASE)
        base.status = PayoutStatus.PAID
        base.paid_date = date(2026, 6, 25)
        base.save(update_fields=["status", "paid_date"])
        receipt = PaymentFactory(
            lease__owner_agreement=agreement,
            amount=Decimal("700.00"),
            currency=Currency.USD,
            payment_date=date(2026, 7, 3),
            due_date=date(2026, 6, 1),
            rental_period=date(2026, 6, 1),
            status=PaymentStatus.PAID,
        )

        settlement = allocate_paid_rent(receipt)
        adjustment = settlement.payouts.get(kind=PayoutKind.UPSIDE_ADJUSTMENT)

        assert adjustment.amount == Decimal("160.00")
        assert adjustment.scheduled_date == date(2026, 7, 25)

    def test_prorates_first_month_and_is_idempotent(self):
        agreement = OwnerAgreementFactory(
            start_date=date(2026, 6, 16),
            end_date=date(2026, 6, 30),
            gross_floor_amount=Decimal("600.00"),
            commission_rate=Decimal("10.00"),
        )
        assert ensure_monthly_settlements(date(2026, 6, 30)) == 1
        assert ensure_monthly_settlements(date(2026, 6, 30)) == 0
        settlement = OwnerSettlement.objects.get(owner_agreement=agreement)
        assert settlement.settlement_base_amount == Decimal("300.00")
        assert settlement.owner_payout_amount == Decimal("270.00")

    def test_prorating_rounds_to_money_precision(self):
        agreement = OwnerAgreementFactory(
            start_date=date(2026, 7, 17),
            end_date=date(2026, 7, 31),
            gross_floor_amount=Decimal("600.00"),
            commission_rate=Decimal("10.00"),
        )

        ensure_monthly_settlements(date(2026, 7, 31))
        settlement = OwnerSettlement.objects.get(owner_agreement=agreement)

        assert settlement.covered_days == 15
        assert settlement.settlement_base_amount == Decimal("290.32")
        assert settlement.commission_amount == Decimal("29.03")
        assert settlement.owner_payout_amount == Decimal("261.29")
