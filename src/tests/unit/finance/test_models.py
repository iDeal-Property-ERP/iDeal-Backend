import pytest
from finance.models import ExchangeRate, Payment, PayoutSchedule

from core.constants import Currency, PaymentMethod, PaymentStatus, PayoutStatus
from tests.factories import ExchangeRateFactory, PaymentFactory, PayoutScheduleFactory


@pytest.mark.django_db
class TestPaymentModel:
    def test_create_payment(self):
        payment = PaymentFactory()
        assert payment.status == PaymentStatus.PENDING
        assert payment.amount == 500.00
        assert payment.currency == Currency.USD
        assert payment.method == PaymentMethod.CASH
        assert str(payment).startswith("Payment #")
        assert payment.tenant is not None
        assert payment.lease is not None
        assert payment.paid_by is not None

    def test_payment_soft_delete(self):
        payment = PaymentFactory()
        payment_id = payment.id
        payment.delete()
        assert payment.deleted_at is not None
        assert not Payment.objects.filter(id=payment_id).exists()
        assert Payment.deleted_objects.filter(id=payment_id).exists()

    def test_payment_default_status(self):
        payment = PaymentFactory(status=PaymentStatus.PENDING)
        assert payment.status == PaymentStatus.PENDING

    def test_payment_mark_paid(self):
        payment = PaymentFactory(status=PaymentStatus.PENDING)
        payment.status = PaymentStatus.PAID
        payment.save()
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.PAID


@pytest.mark.django_db
class TestExchangeRateModel:
    def test_create_exchange_rate(self):
        rate = ExchangeRateFactory(currency=Currency.USD, rate=12500.00)
        assert rate.currency == Currency.USD
        assert rate.rate == 12500.00
        assert rate.effective_date is not None
        assert "USD" in str(rate)
        assert "12500" in str(rate)

    def test_exchange_rate_soft_delete(self):
        rate = ExchangeRateFactory()
        rate_id = rate.id
        rate.delete()
        assert rate.deleted_at is not None
        assert not ExchangeRate.objects.filter(id=rate_id).exists()

    def test_exchange_rate_ordering_by_date(self):
        from datetime import date

        ExchangeRateFactory(currency=Currency.USD, rate=13000.00, effective_date=date(2026, 6, 1))
        ExchangeRateFactory(currency=Currency.USD, rate=12000.00, effective_date=date(2026, 1, 1))
        rates = list(ExchangeRate.objects.all())
        assert rates[0].effective_date >= rates[1].effective_date


@pytest.mark.django_db
class TestPayoutScheduleModel:
    def test_create_payout_schedule(self):
        payout = PayoutScheduleFactory()
        assert payout.status == PayoutStatus.SCHEDULED
        assert payout.amount == 380.00
        assert payout.currency == Currency.USD
        assert payout.paid_date is None
        assert payout.owner_agreement is not None
        assert payout.owner is not None
        assert str(payout).startswith("Payout #")

    def test_payout_soft_delete(self):
        payout = PayoutScheduleFactory()
        payout_id = payout.id
        payout.delete()
        assert payout.deleted_at is not None
        assert not PayoutSchedule.objects.filter(id=payout_id).exists()

    def test_payout_mark_paid(self):
        from datetime import date

        payout = PayoutScheduleFactory(status=PayoutStatus.SCHEDULED)
        payout.status = PayoutStatus.PAID
        payout.paid_date = date.today()
        payout.save()
        payout.refresh_from_db()
        assert payout.status == PayoutStatus.PAID
        assert payout.paid_date is not None
