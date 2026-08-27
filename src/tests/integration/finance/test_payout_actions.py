import json
from datetime import date

import pytest
from finance.models import OwnerSettlement, PayoutSchedule
from notification.models import Notification

from core.constants import NotificationType, PaymentStatus, PayoutStatus
from tests.factories import (
    OwnerAgreementFactory,
    OwnerFactory,
    PaymentFactory,
    PayoutScheduleFactory,
    UserFactory,
)
from tests.integration.property.test_api import _make_jwt


def _json_post(api_client, url, payload, user):
    return api_client.post(url, json.dumps(payload), content_type="application/json", **_make_jwt(user))


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
        agreement = OwnerAgreementFactory(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
        payment = PaymentFactory(
            lease__owner_agreement=agreement,
            status=PaymentStatus.PENDING,
            due_date=date(2026, 6, 1),
            payment_date=date(2026, 6, 10),
            rental_period=date(2026, 6, 1),
        )

        response = api_client.post(f"/api/v1/finance/payments/{payment.id}/mark-paid/", **_make_jwt(mgmt))

        assert response.status_code == 200
        payouts = PayoutSchedule.objects.filter(settlement__owner_agreement=agreement)
        assert payouts.count() == 1
        assert payouts.first().amount == agreement.gross_floor_amount * (1 - agreement.commission_rate / 100)
        assert Notification.objects.filter(recipient=payment.tenant, type=NotificationType.PAYMENT_PAID).exists()

    def test_paid_payment_does_not_double_accrue_on_resave(self, api_client):
        agreement = OwnerAgreementFactory(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
        payment = PaymentFactory(
            lease__owner_agreement=agreement,
            status=PaymentStatus.PAID,
            due_date=date(2026, 6, 1),
            payment_date=date(2026, 6, 10),
            rental_period=date(2026, 6, 1),
        )
        # Re-save the already-paid payment; signal must not create a second payout.
        payment.save()
        assert OwnerSettlement.objects.filter(owner_agreement=agreement).count() == 1
        assert PayoutSchedule.objects.filter(settlement__owner_agreement=agreement).count() == 1


@pytest.mark.django_db
class TestPayoutHoldRelease:
    def test_hold_requires_reason(self, api_client):
        mgmt = UserFactory()
        payout = PayoutScheduleFactory(status=PayoutStatus.SCHEDULED)
        response = _json_post(api_client, f"/api/v1/finance/payouts/{payout.id}/hold/", {}, mgmt)
        assert response.status_code == 400

    def test_hold_then_release(self, api_client):
        mgmt = UserFactory()
        payout = PayoutScheduleFactory(status=PayoutStatus.SCHEDULED)
        held = _json_post(
            api_client, f"/api/v1/finance/payouts/{payout.id}/hold/", {"reason": "bank details invalid"}, mgmt
        )
        assert held.status_code == 200
        payout.refresh_from_db()
        assert payout.status == PayoutStatus.HELD
        assert payout.status_reason == "bank details invalid"

        released = api_client.post(f"/api/v1/finance/payouts/{payout.id}/release/", **_make_jwt(mgmt))
        assert released.status_code == 200
        payout.refresh_from_db()
        assert payout.status == PayoutStatus.SCHEDULED
        assert payout.status_reason is None

    def test_hold_invalid_from_paid(self, api_client):
        mgmt = UserFactory()
        payout = PayoutScheduleFactory(status=PayoutStatus.PAID)
        response = _json_post(api_client, f"/api/v1/finance/payouts/{payout.id}/hold/", {"reason": "x"}, mgmt)
        assert response.status_code == 400

    def test_release_invalid_from_scheduled(self, api_client):
        mgmt = UserFactory()
        payout = PayoutScheduleFactory(status=PayoutStatus.SCHEDULED)
        response = api_client.post(f"/api/v1/finance/payouts/{payout.id}/release/", **_make_jwt(mgmt))
        assert response.status_code == 400


@pytest.mark.django_db
class TestPayoutCancelReason:
    def test_cancel_persists_reason(self, api_client):
        mgmt = UserFactory()
        payout = PayoutScheduleFactory(status=PayoutStatus.SCHEDULED)
        response = _json_post(api_client, f"/api/v1/finance/payouts/{payout.id}/cancel/", {"reason": "reissuing"}, mgmt)
        assert response.status_code == 200
        payout.refresh_from_db()
        assert payout.status == PayoutStatus.CANCELLED
        assert payout.status_reason == "reissuing"


@pytest.mark.django_db
class TestPayoutManualCreate:
    def test_create_manual_payout(self, api_client, property_obj):
        mgmt = UserFactory()
        agreement = OwnerAgreementFactory(property=property_obj)
        response = _json_post(
            api_client,
            "/api/v1/finance/payouts/",
            {
                "owner_agreement_id": agreement.id,
                "amount": "380.00",
                "currency": "USD",
                "scheduled_date": "2026-07-25",
                "method": "bank_transfer",
            },
            mgmt,
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["owner_id"] == agreement.owner_id
        assert data["settlement_id"] is None


@pytest.mark.django_db
class TestPayoutBulkMarkPaid:
    def test_bulk_mark_paid_mixed(self, api_client):
        mgmt = UserFactory()
        scheduled = PayoutScheduleFactory(status=PayoutStatus.SCHEDULED)
        held = PayoutScheduleFactory(status=PayoutStatus.HELD)
        already = PayoutScheduleFactory(status=PayoutStatus.PAID)
        response = _json_post(
            api_client,
            "/api/v1/finance/payouts/bulk-mark-paid/",
            {"ids": [scheduled.id, held.id, already.id, 999999]},
            mgmt,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["updated"] == 2
        assert data["skipped"] == 2


@pytest.mark.django_db
class TestPaymentBulkAndRemind:
    def test_bulk_mark_paid_allocates_settlements(self, api_client):
        mgmt = UserFactory()
        agreement = OwnerAgreementFactory(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
        defaults = {
            "lease__owner_agreement": agreement,
            "due_date": date(2026, 6, 1),
            "payment_date": date(2026, 6, 10),
            "rental_period": date(2026, 6, 1),
        }
        p1 = PaymentFactory(status=PaymentStatus.PENDING, **defaults)
        p2 = PaymentFactory(status=PaymentStatus.OVERDUE, **defaults)
        paid = PaymentFactory(status=PaymentStatus.PAID, **defaults)
        response = _json_post(
            api_client,
            "/api/v1/finance/payments/bulk-mark-paid/",
            {"ids": [p1.id, p2.id, paid.id]},
            mgmt,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["updated"] == 2
        assert data["skipped"] == 1
        assert OwnerSettlement.objects.filter(owner_agreement=agreement).count() == 1

    def test_bulk_remind(self, api_client):
        mgmt = UserFactory()
        p1 = PaymentFactory(status=PaymentStatus.OVERDUE)
        paid = PaymentFactory(status=PaymentStatus.PAID)
        response = _json_post(
            api_client,
            "/api/v1/finance/payments/bulk-remind/",
            {"ids": [p1.id, paid.id]},
            mgmt,
        )
        assert response.status_code == 200
        assert response.json()["data"]["sent"] == 1
        assert Notification.objects.filter(recipient=p1.tenant, type=NotificationType.PAYMENT_DUE).exists()

    def test_single_remind(self, api_client):
        mgmt = UserFactory()
        payment = PaymentFactory(status=PaymentStatus.PENDING)
        response = api_client.post(f"/api/v1/finance/payments/{payment.id}/remind/", **_make_jwt(mgmt))
        assert response.status_code == 200
        assert response.json()["data"]["sent"] == 1


@pytest.mark.django_db
class TestPaymentGatewayValidation:
    def test_bank_transfer_requires_reference(self, api_client, property_obj):
        from tests.factories import LeaseFactory, OwnerAgreementFactory, TenantFactory

        mgmt = UserFactory()
        tenant = TenantFactory()
        agreement = OwnerAgreementFactory(property=property_obj)
        lease = LeaseFactory(property=property_obj, owner_agreement=agreement, tenant=tenant, status="active")
        base = {
            "lease_id": lease.id,
            "tenant_id": tenant.id,
            "paid_by_id": tenant.id,
            "amount": "500.00",
            "currency": "USD",
            "payment_date": "2026-06-01",
            "due_date": "2026-07-01",
            "status": "pending",
            "method": "bank_transfer",
        }
        missing = _json_post(api_client, "/api/v1/finance/payments/", base, mgmt)
        assert missing.status_code == 400

        ok = _json_post(api_client, "/api/v1/finance/payments/", {**base, "gateway_ref": "TRX-123"}, mgmt)
        assert ok.status_code == 201
