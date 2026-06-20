import json
from decimal import Decimal

import pytest
from finance.models import Payment

from core.constants import LeaseStatus, PaymentStatus
from tests.factories import LeaseFactory, PropertyFactory, TenantFactory
from tests.integration.property.test_api import _make_jwt


@pytest.mark.django_db
class TestTenantPayNow:
    def test_pay_now_creates_pending_payment_default_amount(self, api_client):
        tenant = TenantFactory()
        prop = PropertyFactory(tenant_charge_price=Decimal("550.00"), tenant_charge_currency="USD")
        lease = LeaseFactory(tenant=tenant, property=prop, status=LeaseStatus.ACTIVE, monthly_rent=Decimal("550.00"))

        response = api_client.post(
            "/api/v1/tenant/payments/",
            data=json.dumps({"method": "online"}),
            content_type="application/json",
            **_make_jwt(tenant),
        )

        assert response.status_code in (200, 201)
        body = response.json()
        assert body["success"] is True
        payment = Payment.objects.get(lease=lease)
        assert payment.status == PaymentStatus.PENDING
        assert payment.amount == Decimal("550.00")
        assert payment.method == "online"
        assert payment.paid_by_id == tenant.id

    def test_pay_now_custom_amount(self, api_client):
        tenant = TenantFactory()
        LeaseFactory(tenant=tenant, status=LeaseStatus.ACTIVE)

        response = api_client.post(
            "/api/v1/tenant/payments/",
            data=json.dumps({"amount": "123.45"}),
            content_type="application/json",
            **_make_jwt(tenant),
        )

        assert response.status_code in (200, 201)
        payment = Payment.objects.get(tenant=tenant)
        assert payment.amount == Decimal("123.45")

    def test_pay_now_without_active_lease_fails(self, api_client):
        tenant = TenantFactory()

        response = api_client.post(
            "/api/v1/tenant/payments/",
            data=json.dumps({}),
            content_type="application/json",
            **_make_jwt(tenant),
        )

        assert response.status_code == 400
        assert response.json()["success"] is False

    def test_pay_now_rbac(self, api_client):
        from tests.factories import OwnerFactory

        owner = OwnerFactory()
        response = api_client.post(
            "/api/v1/tenant/payments/",
            data=json.dumps({}),
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 403
