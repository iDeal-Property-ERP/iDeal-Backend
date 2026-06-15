import json

import pytest
from django.conf import settings

from core.constants import Currency, PaymentStatus, PayoutStatus
from tests.factories import ExchangeRateFactory, PaymentFactory, PayoutScheduleFactory


def _make_jwt(user):
    from datetime import UTC, datetime, timedelta

    import jwt

    payload = {
        "sub": str(user.id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "token_type": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.mark.django_db
class TestPaymentAPI:
    def test_create_payment(self, api_client, management, tenant, property_obj):
        from tests.factories import LeaseFactory, OwnerAgreementFactory

        agreement = OwnerAgreementFactory(property=property_obj)
        lease = LeaseFactory(
            property=property_obj,
            owner_agreement=agreement,
            tenant=tenant,
            status="active",
        )

        payload = json.dumps(
            {
                "lease_id": lease.id,
                "tenant_id": tenant.id,
                "paid_by_id": tenant.id,
                "amount": "500.00",
                "currency": "USD",
                "payment_date": "2026-06-01",
                "due_date": "2026-07-01",
                "status": "pending",
                "method": "cash",
            }
        )
        response = api_client.post(
            "/api/v1/finance/payments/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "pending"
        assert body["data"]["amount"] == "500.00"
        assert body["data"]["lease_id"] == lease.id

    def test_create_payment_requires_auth(self, api_client, tenant, property_obj):
        from tests.factories import LeaseFactory, OwnerAgreementFactory

        agreement = OwnerAgreementFactory(property=property_obj)
        lease = LeaseFactory(
            property=property_obj,
            owner_agreement=agreement,
            tenant=tenant,
        )
        payload = json.dumps(
            {
                "lease_id": lease.id,
                "tenant_id": tenant.id,
                "paid_by_id": tenant.id,
                "amount": "500.00",
                "currency": "USD",
                "payment_date": "2026-06-01",
                "due_date": "2026-07-01",
            }
        )
        response = api_client.post(
            "/api/v1/finance/payments/",
            payload,
            content_type="application/json",
        )
        assert response.status_code in (401, 403)

    def test_list_payments(self, api_client, management):
        PaymentFactory()
        PaymentFactory()
        response = api_client.get(
            "/api/v1/finance/payments/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 2

    def test_list_payments_requires_auth(self, api_client):
        response = api_client.get("/api/v1/finance/payments/")
        assert response.status_code in (401, 403)

    def test_partial_update_payment(self, api_client, management):
        payment = PaymentFactory(status=PaymentStatus.PENDING, notes="original")
        payload = json.dumps({"notes": "updated notes"})
        response = api_client.patch(
            f"/api/v1/finance/payments/{payment.id}/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["notes"] == "updated notes"

    def test_mark_paid(self, api_client, management):
        payment = PaymentFactory(status=PaymentStatus.PENDING)
        response = api_client.post(
            f"/api/v1/finance/payments/{payment.id}/mark-paid/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "paid"

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.PAID

    def test_mark_paid_already_paid(self, api_client, management):
        payment = PaymentFactory(status=PaymentStatus.PAID)
        response = api_client.post(
            f"/api/v1/finance/payments/{payment.id}/mark-paid/",
            **_make_jwt(management),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False

    def test_mark_paid_404(self, api_client, management):
        response = api_client.post(
            "/api/v1/finance/payments/99999/mark-paid/",
            **_make_jwt(management),
        )
        assert response.status_code == 404

    def test_invalid_payment_data(self, api_client, management):
        payload = json.dumps({"lease_id": 1})
        response = api_client.post(
            "/api/v1/finance/payments/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert "error" in body


@pytest.mark.django_db
class TestExchangeRateAPI:
    def test_create_exchange_rate(self, api_client, management):
        payload = json.dumps(
            {
                "currency": "USD",
                "rate": "12500.0000",
                "effective_date": "2026-06-01",
            }
        )
        response = api_client.post(
            "/api/v1/finance/exchange-rates/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["currency"] == "USD"

    def test_list_exchange_rates(self, api_client, management):
        ExchangeRateFactory(currency=Currency.USD)
        ExchangeRateFactory(currency=Currency.UZS, rate=1.0000)
        response = api_client.get(
            "/api/v1/finance/exchange-rates/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 2

    def test_create_exchange_rate_requires_auth(self, api_client):
        payload = json.dumps(
            {
                "currency": "USD",
                "rate": "12500.0000",
                "effective_date": "2026-06-01",
            }
        )
        response = api_client.post(
            "/api/v1/finance/exchange-rates/",
            payload,
            content_type="application/json",
        )
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestPayoutAPI:
    def test_list_payouts(self, api_client, management):
        PayoutScheduleFactory()
        PayoutScheduleFactory()
        response = api_client.get(
            "/api/v1/finance/payouts/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 2

    def test_list_payouts_requires_auth(self, api_client):
        response = api_client.get("/api/v1/finance/payouts/")
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestDashboardAPI:
    def test_dashboard(self, api_client, management):
        ExchangeRateFactory(currency=Currency.USD, rate=12500.00)
        PaymentFactory(status=PaymentStatus.PAID, amount=500.00, currency=Currency.USD)
        PaymentFactory(status=PaymentStatus.PENDING, amount=300.00, currency=Currency.USD)
        PayoutScheduleFactory(status=PayoutStatus.PAID, amount=380.00, currency=Currency.USD)

        response = api_client.get(
            "/api/v1/finance/dashboard/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "total_payments" in data
        assert "total_payments_uzs" in data
        assert "total_payouts" in data
        assert "total_payouts_uzs" in data
        assert "net_margin" in data
        assert "net_margin_uzs" in data
        assert data["pending_count"] >= 1
        assert data["overdue_count"] >= 0

    def test_dashboard_no_data(self, api_client, management):
        response = api_client.get(
            "/api/v1/finance/dashboard/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["total_payments"] == "0.00"
        assert data["net_margin"] == "0.00"

    def test_dashboard_requires_auth(self, api_client):
        response = api_client.get("/api/v1/finance/dashboard/")
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestPnLAPI:
    def test_pnl(self, api_client, management):
        ExchangeRateFactory(currency=Currency.USD, rate=12500.00)
        PaymentFactory(
            status=PaymentStatus.PAID,
            amount=500.00,
            currency=Currency.USD,
            payment_date="2026-06-15",
        )
        PayoutScheduleFactory(
            status=PayoutStatus.PAID,
            amount=380.00,
            currency=Currency.USD,
            paid_date="2026-06-15",
        )

        response = api_client.get(
            "/api/v1/finance/pnl/?year=2026&month=6",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "gross_revenue" in data
        assert "gross_revenue_uzs" in data
        assert "owner_payouts" in data
        assert "net_margin" in data
        assert "tax_estimate" in data
        assert data["payment_count"] >= 1

    def test_pnl_no_filters(self, api_client, management):
        ExchangeRateFactory(currency=Currency.USD, rate=12500.00)
        PaymentFactory(status=PaymentStatus.PAID, amount=500.00, currency=Currency.USD)
        PayoutScheduleFactory(status=PayoutStatus.PAID, amount=380.00, currency=Currency.USD)

        response = api_client.get(
            "/api/v1/finance/pnl/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

    def test_pnl_requires_auth(self, api_client):
        response = api_client.get("/api/v1/finance/pnl/")
        assert response.status_code in (401, 403)
