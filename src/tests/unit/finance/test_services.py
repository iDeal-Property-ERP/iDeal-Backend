from datetime import date
from decimal import Decimal

import pytest
from finance.models import PayoutSchedule
from finance.services import _next_payout_date, accrue_owner_payout_for_payment

from core.constants import Currency, PaymentStatus, PayoutStatus
from tests.factories import PaymentFactory, PropertyFactory


@pytest.mark.django_db
class TestAccrueOwnerPayout:
    def test_accrues_owner_guaranteed_amount(self):
        prop = PropertyFactory(owner_guaranteed_price=Decimal("400.00"))
        payment = PaymentFactory(status=PaymentStatus.PENDING)
        payment.lease.owner_agreement.property = prop
        payment.lease.owner_agreement.save()
        payment.status = PaymentStatus.PAID
        payment.save()

        payout = PayoutSchedule.objects.get(source_payment=payment)
        assert payout.amount == Decimal("400.00")
        assert payout.currency == Currency.USD
        assert payout.status == PayoutStatus.SCHEDULED
        assert payout.owner_id == payment.lease.owner_agreement.owner_id

    def test_idempotent_no_double_payout(self):
        payment = PaymentFactory(status=PaymentStatus.PAID)
        # Signal already accrued one on save; calling again must not duplicate.
        accrue_owner_payout_for_payment(payment)
        accrue_owner_payout_for_payment(payment)
        assert PayoutSchedule.objects.filter(source_payment=payment).count() == 1

    def test_no_accrual_when_not_paid(self):
        payment = PaymentFactory(status=PaymentStatus.PENDING)
        result = accrue_owner_payout_for_payment(payment)
        assert result is None
        assert PayoutSchedule.objects.filter(source_payment=payment).count() == 0


class TestNextPayoutDate:
    def test_same_month_before_day(self):
        assert _next_payout_date(date(2026, 6, 10)) == date(2026, 6, 25)

    def test_rolls_to_next_month_after_day(self):
        assert _next_payout_date(date(2026, 6, 26)) == date(2026, 7, 25)

    def test_year_rollover(self):
        assert _next_payout_date(date(2026, 12, 27)) == date(2027, 1, 25)
