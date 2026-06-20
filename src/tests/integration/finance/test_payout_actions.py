import pytest
from finance.models import PayoutSchedule
from notification.models import Notification

from core.constants import NotificationType, PaymentStatus, PayoutStatus
from tests.factories import (
    OwnerFactory,
    PaymentFactory,
    PayoutScheduleFactory,
    UserFactory,
)
from tests.integration.property.test_api import _make_jwt


@pytest.mark.django_db
class TestPayoutMarkPaid:
    def test_mark_paid_success(self, api_client):
        mgmt = UserFactory()
        payout = PayoutScheduleFactory(status=PayoutStatus.SCHEDULED)

        response = api_client.post(f"/api/v1/finance/payouts/{payout.id}/mark-paid/", **_make_jwt(mgmt))

        assert response.status_code == 200
        payout.refresh_from_db()
        assert payout.status == PayoutStatus.PAID
        assert payout.paid_date is not None
        assert Notification.objects.filter(recipient=payout.owner, type=NotificationType.PAYOUT_PAID).exists()

    def test_mark_paid_already_paid_fails(self, api_client):
        mgmt = UserFactory()
        payout = PayoutScheduleFactory(status=PayoutStatus.PAID)

        response = api_client.post(f"/api/v1/finance/payouts/{payout.id}/mark-paid/", **_make_jwt(mgmt))

        assert response.status_code == 400
        assert response.json()["success"] is False

    def test_mark_paid_rbac(self, api_client):
        owner = OwnerFactory()
        payout = PayoutScheduleFactory(status=PayoutStatus.SCHEDULED)

        response = api_client.post(f"/api/v1/finance/payouts/{payout.id}/mark-paid/", **_make_jwt(owner))

        assert response.status_code == 403


@pytest.mark.django_db
class TestTransitFinanceSignal:
    def test_marking_payment_paid_accrues_single_payout(self, api_client):
        mgmt = UserFactory()
        payment = PaymentFactory(status=PaymentStatus.PENDING)

        response = api_client.post(f"/api/v1/finance/payments/{payment.id}/mark-paid/", **_make_jwt(mgmt))

        assert response.status_code == 200
        payouts = PayoutSchedule.objects.filter(source_payment=payment)
        assert payouts.count() == 1
        assert payouts.first().amount == payment.lease.owner_agreement.property.owner_guaranteed_price
        assert Notification.objects.filter(recipient=payment.tenant, type=NotificationType.PAYMENT_PAID).exists()

    def test_paid_payment_does_not_double_accrue_on_resave(self, api_client):
        payment = PaymentFactory(status=PaymentStatus.PAID)
        # Re-save the already-paid payment; signal must not create a second payout.
        payment.save()
        assert PayoutSchedule.objects.filter(source_payment=payment).count() == 1
