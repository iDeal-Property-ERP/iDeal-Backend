import json
from decimal import Decimal

import pytest

from core.constants import LeaseStatus
from tests.factories import (
    DistrictFactory,
    LeaseFactory,
    OwnerFactory,
    PaymentFactory,
    PropertyFactory,
    TenantFactory,
    UserFactory,
)


@pytest.mark.django_db
class TestTenantHomeAPI:
    def test_tenant_home_with_active_lease(self, api_client):
        tenant = TenantFactory()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        lease = LeaseFactory(tenant=tenant, property=prop, status=LeaseStatus.ACTIVE)
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/tenant/home/", **_make_jwt(tenant))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["lease_id"] == lease.id
        assert data["property_id"] == prop.id
        assert data["property_name"] == prop.name
        assert Decimal(data["monthly_rent"]) == Decimal(str(lease.monthly_rent))

    def test_tenant_home_no_active_lease(self, api_client):
        tenant = TenantFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/tenant/home/", **_make_jwt(tenant))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["lease_id"] is None

    def test_tenant_home_rbac(self, api_client):
        owner = OwnerFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/tenant/home/", **_make_jwt(owner))
        assert response.status_code == 403

    def test_tenant_home_requires_auth(self, api_client):
        response = api_client.get("/api/v1/tenant/home/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestTenantPaymentsAPI:
    def test_tenant_payment_list(self, api_client):
        tenant = TenantFactory()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        lease = LeaseFactory(tenant=tenant, property=prop)
        paid_by = UserFactory()
        PaymentFactory(tenant=tenant, lease=lease, paid_by=paid_by, amount=500.00)
        PaymentFactory(tenant=tenant, lease=lease, paid_by=paid_by, amount=600.00)
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/tenant/payments/", **_make_jwt(tenant))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 2

    def test_tenant_payment_list_empty(self, api_client):
        tenant = TenantFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/tenant/payments/", **_make_jwt(tenant))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    def test_tenant_payments_rbac(self, api_client):
        owner = OwnerFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/tenant/payments/", **_make_jwt(owner))
        assert response.status_code == 403

    def test_tenant_payment_placeholder(self, api_client):
        tenant = TenantFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.post(
            "/api/v1/tenant/payments/",
            data=json.dumps({}),
            content_type="application/json",
            **_make_jwt(tenant),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert "coming soon" in body["data"]["message"].lower()


@pytest.mark.django_db
class TestTenantServiceRequestsAPI:
    def test_tenant_create_service_request(self, api_client):
        tenant = TenantFactory()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        LeaseFactory(tenant=tenant, property=prop, status=LeaseStatus.ACTIVE)
        from tests.integration.property.test_api import _make_jwt

        payload = {
            "property_id": prop.id,
            "title": "Leaky faucet",
            "description": "Kitchen sink is leaking",
            "priority": "high",
        }
        response = api_client.post(
            "/api/v1/tenant/service-requests/",
            data=json.dumps(payload),
            content_type="application/json",
            **_make_jwt(tenant),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["title"] == "Leaky faucet"
        assert body["data"]["property_id"] == prop.id
        assert body["data"]["status"] == "open"

    def test_tenant_create_service_request_not_their_property(self, api_client):
        tenant = TenantFactory()
        district = DistrictFactory()
        owner = OwnerFactory()
        other_prop = PropertyFactory(owner=owner, district=district)
        from tests.integration.property.test_api import _make_jwt

        payload = {
            "property_id": other_prop.id,
            "title": "Broken window",
            "description": "Window won't close",
        }
        response = api_client.post(
            "/api/v1/tenant/service-requests/",
            data=json.dumps(payload),
            content_type="application/json",
            **_make_jwt(tenant),
        )
        assert response.status_code == 403

    def test_tenant_create_service_request_validation_error(self, api_client):
        tenant = TenantFactory()
        from tests.integration.property.test_api import _make_jwt

        payload = {"property_id": "invalid"}
        response = api_client.post(
            "/api/v1/tenant/service-requests/",
            data=json.dumps(payload),
            content_type="application/json",
            **_make_jwt(tenant),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert "error" in body

    def test_tenant_list_service_requests(self, api_client):
        tenant = TenantFactory()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        LeaseFactory(tenant=tenant, property=prop, status=LeaseStatus.ACTIVE)
        from maintenance.models import ServiceRequest

        ServiceRequest.objects.create(property=prop, tenant=tenant, title="Issue 1", description="Desc 1")
        ServiceRequest.objects.create(property=prop, tenant=tenant, title="Issue 2", description="Desc 2")
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/tenant/service-requests/", **_make_jwt(tenant))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 2

    def test_tenant_service_requests_rbac(self, api_client):
        owner = OwnerFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/tenant/service-requests/", **_make_jwt(owner))
        assert response.status_code == 403

    def test_tenant_service_requests_requires_auth(self, api_client):
        response = api_client.get("/api/v1/tenant/service-requests/")
        assert response.status_code == 401
