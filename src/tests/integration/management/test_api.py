import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from django.conf import settings

from core.constants import LeaseStatus, OwnerAgreementStatus, ServiceRequestStatus, UserRole
from tests.factories import (
    DistrictFactory,
    LeaseFactory,
    OwnerAgreementFactory,
    OwnerFactory,
    PaymentFactory,
    PayoutScheduleFactory,
    PropertyFactory,
    ServiceRequestFactory,
    TenantFactory,
    UserFactory,
)


def _make_jwt(user):
    payload = {
        "sub": str(user.id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "token_type": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _mgmt_user():
    return UserFactory(role=UserRole.MANAGEMENT)


@pytest.mark.django_db
class TestManagementDashboardAPI:
    def test_dashboard_success(self, api_client):
        mgmt = _mgmt_user()
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "users" in data
        assert "properties" in data
        assert "active_leases" in data
        assert "active_agreements" in data
        assert "revenue_collected" in data
        assert "pending_payouts" in data
        assert "open_service_requests" in data

    def test_dashboard_rbac(self, api_client):
        owner = OwnerFactory()
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(owner))
        assert response.status_code == 403

    def test_dashboard_requires_auth(self, api_client):
        response = api_client.get("/api/v1/management/dashboard/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestManagementUserListAPI:
    def test_list_all_users(self, api_client):
        mgmt = _mgmt_user()
        UserFactory(role=UserRole.OWNER)
        UserFactory(role=UserRole.TENANT)
        response = api_client.get("/api/v1/management/users/", **_make_jwt(mgmt))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) >= 3

    def test_list_filter_by_role(self, api_client):
        mgmt = _mgmt_user()
        UserFactory(role=UserRole.OWNER)
        UserFactory(role=UserRole.TENANT)
        response = api_client.get(f"/api/v1/management/users/?role={UserRole.OWNER}", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(u["role"] == UserRole.OWNER for u in data)

    def test_list_search(self, api_client):
        mgmt = _mgmt_user()
        UserFactory(first_name="Alice", role=UserRole.OWNER)
        UserFactory(first_name="Bob", role=UserRole.TENANT)
        response = api_client.get("/api/v1/management/users/?search=Alice", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert any(u["first_name"] == "Alice" for u in data)

    def test_list_rbac(self, api_client):
        tenant = TenantFactory()
        response = api_client.get("/api/v1/management/users/", **_make_jwt(tenant))
        assert response.status_code == 403

    def test_list_requires_auth(self, api_client):
        response = api_client.get("/api/v1/management/users/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestManagementUserUpdateAPI:
    def test_patch_user(self, api_client):
        mgmt = _mgmt_user()
        target = UserFactory(role=UserRole.TENANT, is_active=True, is_verified=False)
        response = api_client.patch(
            f"/api/v1/management/users/{target.id}/",
            data=json.dumps({"is_active": False, "is_verified": True, "role": UserRole.OWNER}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["is_active"] is False
        assert body["data"]["is_verified"] is True
        assert body["data"]["role"] == UserRole.OWNER

    def test_patch_user_not_found(self, api_client):
        mgmt = _mgmt_user()
        response = api_client.patch(
            "/api/v1/management/users/99999/",
            data=json.dumps({"is_active": False}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert response.status_code == 404

    def test_patch_user_rbac(self, api_client):
        owner = OwnerFactory()
        target = UserFactory()
        response = api_client.patch(
            f"/api/v1/management/users/{target.id}/",
            data=json.dumps({"is_active": False}),
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 403

    def test_patch_user_requires_auth(self, api_client):
        response = api_client.patch(
            "/api/v1/management/users/1/",
            data=json.dumps({"is_active": False}),
            content_type="application/json",
        )
        assert response.status_code == 401


@pytest.mark.django_db
class TestManagementPropertyListAPI:
    def test_list_properties(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        PropertyFactory(district=district, owner=owner)
        PropertyFactory(district=district, owner=owner)
        response = api_client.get("/api/v1/management/properties/", **_make_jwt(mgmt))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) >= 2

    def test_list_properties_filter_by_status(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        PropertyFactory(district=district, owner=owner, status="vacant")
        PropertyFactory(district=district, owner=owner, status="rented")
        response = api_client.get("/api/v1/management/properties/?status=vacant", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(p["status"] == "vacant" for p in data)

    def test_list_properties_rbac(self, api_client):
        tenant = TenantFactory()
        response = api_client.get("/api/v1/management/properties/", **_make_jwt(tenant))
        assert response.status_code == 403

    def test_list_properties_requires_auth(self, api_client):
        response = api_client.get("/api/v1/management/properties/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestManagementLeaseListAPI:
    def test_list_leases(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        prop = PropertyFactory(owner=owner, district=district)
        LeaseFactory(property=prop, tenant=tenant)
        response = api_client.get("/api/v1/management/leases/", **_make_jwt(mgmt))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) >= 1

    def test_list_leases_filter_by_status(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        prop = PropertyFactory(owner=owner, district=district)
        LeaseFactory(property=prop, tenant=tenant, status=LeaseStatus.ACTIVE)
        LeaseFactory(property=prop, tenant=tenant, status=LeaseStatus.EXPIRED)
        response = api_client.get(f"/api/v1/management/leases/?status={LeaseStatus.ACTIVE}", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(ls["status"] == LeaseStatus.ACTIVE for ls in data)

    def test_list_leases_rbac(self, api_client):
        owner = OwnerFactory()
        response = api_client.get("/api/v1/management/leases/", **_make_jwt(owner))
        assert response.status_code == 403


@pytest.mark.django_db
class TestManagementOwnerAgreementListAPI:
    def test_list_agreements(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        OwnerAgreementFactory(owner=owner, property=prop)
        response = api_client.get("/api/v1/management/owner-agreements/", **_make_jwt(mgmt))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) >= 1

    def test_list_agreements_filter_by_status(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        OwnerAgreementFactory(owner=owner, property=prop, status=OwnerAgreementStatus.ACTIVE)
        OwnerAgreementFactory(owner=owner, property=prop, status=OwnerAgreementStatus.EXPIRED)
        response = api_client.get(
            f"/api/v1/management/owner-agreements/?status={OwnerAgreementStatus.ACTIVE}", **_make_jwt(mgmt)
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(a["status"] == OwnerAgreementStatus.ACTIVE for a in data)

    def test_list_agreements_rbac(self, api_client):
        tenant = TenantFactory()
        response = api_client.get("/api/v1/management/owner-agreements/", **_make_jwt(tenant))
        assert response.status_code == 403


@pytest.mark.django_db
class TestManagementPaymentListAPI:
    def test_list_payments(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        paid_by = UserFactory()
        prop = PropertyFactory(owner=owner, district=district)
        lease = LeaseFactory(property=prop, tenant=tenant)
        PaymentFactory(lease=lease, tenant=tenant, paid_by=paid_by)
        response = api_client.get("/api/v1/management/payments/", **_make_jwt(mgmt))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) >= 1

    def test_list_payments_filter_by_status(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        paid_by = UserFactory()
        prop = PropertyFactory(owner=owner, district=district)
        lease = LeaseFactory(property=prop, tenant=tenant)
        PaymentFactory(lease=lease, tenant=tenant, paid_by=paid_by, status="paid")
        PaymentFactory(lease=lease, tenant=tenant, paid_by=paid_by, status="pending")
        response = api_client.get("/api/v1/management/payments/?status=paid", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(p["status"] == "paid" for p in data)

    def test_list_payments_rbac(self, api_client):
        owner = OwnerFactory()
        response = api_client.get("/api/v1/management/payments/", **_make_jwt(owner))
        assert response.status_code == 403


@pytest.mark.django_db
class TestManagementPayoutListAPI:
    def test_list_payouts(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        agreement = OwnerAgreementFactory(owner=owner, property=prop)
        PayoutScheduleFactory(owner_agreement=agreement, owner=owner)
        response = api_client.get("/api/v1/management/payouts/", **_make_jwt(mgmt))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) >= 1

    def test_list_payouts_filter_by_status(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        agreement = OwnerAgreementFactory(owner=owner, property=prop)
        PayoutScheduleFactory(owner_agreement=agreement, owner=owner, status="paid")
        PayoutScheduleFactory(owner_agreement=agreement, owner=owner, status="scheduled")
        response = api_client.get("/api/v1/management/payouts/?status=paid", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(p["status"] == "paid" for p in data)

    def test_list_payouts_rbac(self, api_client):
        tenant = TenantFactory()
        response = api_client.get("/api/v1/management/payouts/", **_make_jwt(tenant))
        assert response.status_code == 403


@pytest.mark.django_db
class TestManagementServiceRequestListAPI:
    def test_list_service_requests(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        prop = PropertyFactory(owner=owner, district=district)
        ServiceRequestFactory(property=prop, tenant=tenant)
        ServiceRequestFactory(property=prop, tenant=tenant)
        response = api_client.get("/api/v1/management/service-requests/", **_make_jwt(mgmt))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) >= 2

    def test_list_service_requests_filter_by_status(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        prop = PropertyFactory(owner=owner, district=district)
        ServiceRequestFactory(property=prop, tenant=tenant, status=ServiceRequestStatus.OPEN)
        ServiceRequestFactory(property=prop, tenant=tenant, status=ServiceRequestStatus.RESOLVED)
        response = api_client.get(
            f"/api/v1/management/service-requests/?status={ServiceRequestStatus.OPEN}", **_make_jwt(mgmt)
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(sr["status"] == ServiceRequestStatus.OPEN for sr in data)

    def test_list_service_requests_rbac(self, api_client):
        tenant = TenantFactory()
        response = api_client.get("/api/v1/management/service-requests/", **_make_jwt(tenant))
        assert response.status_code == 403
