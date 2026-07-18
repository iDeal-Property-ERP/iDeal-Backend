import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from django.conf import settings

from core.constants import LeaseStatus, OwnerAgreementStatus, ServiceRequestStatus, UserRole
from tests.factories import (
    DistrictFactory,
    ExchangeRateFactory,
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
    def test_dashboard_returns_all_sections(self, api_client):
        mgmt = _mgmt_user()
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "greeting" in data
        assert "date" in data
        assert "location" in data
        assert "total_properties" in data
        assert "payment_status" in data
        assert "kpi" in data
        assert "recent_payments" in data
        assert "occupancy" in data
        assert "brokerage" in data
        assert "maintenance_requests" in data

        kpi = data["kpi"]
        assert "occupied" in kpi
        assert "net_profit" in kpi
        assert "payments_received" in kpi
        assert "vacant" in kpi

        occ = data["occupancy"]
        assert "rate" in occ
        assert "rented" in occ
        assert "vacant" in occ
        assert "maintenance" in occ

        brokerage = data["brokerage"]
        assert "expected_uzs" in brokerage
        assert "received_uzs" in brokerage
        assert "unpaid_uzs" in brokerage
        assert "closed_count" in brokerage

    def test_dashboard_greeting(self, api_client):
        mgmt = _mgmt_user()
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        body = response.json()
        assert f"Xush kelibsiz, {mgmt.first_name}" in body["data"]["greeting"]

    def test_dashboard_kpis_with_data(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        for _ in range(4):
            PropertyFactory(district=district, owner=owner, status="rented")
        for _ in range(2):
            PropertyFactory(district=district, owner=owner, status="vacant")
        PropertyFactory(district=district, owner=owner, status="maintenance")
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        body = response.json()
        data = body["data"]
        assert data["total_properties"] == 7
        assert data["kpi"]["occupied"]["value"] == 4
        assert data["kpi"]["occupied"]["total"] == 7
        assert data["kpi"]["vacant"]["value"] == 2
        assert data["occupancy"]["rented"] == 4
        assert data["occupancy"]["vacant"] == 2
        assert data["occupancy"]["maintenance"] == 1

    def test_dashboard_recent_payments(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        prop = PropertyFactory(district=district, owner=owner)
        lease = LeaseFactory(property=prop, tenant=tenant)
        PaymentFactory(lease=lease, tenant=tenant, status="paid")
        PaymentFactory(lease=lease, tenant=tenant, status="pending")
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        body = response.json()
        payments = body["data"]["recent_payments"]
        assert len(payments) >= 2
        assert payments[0]["id"] is not None
        assert payments[0]["tenant_name"] is not None
        assert payments[0]["property_name"] is not None
        assert payments[0]["amount"] is not None

    def test_dashboard_maintenance_requests(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        prop = PropertyFactory(district=district, owner=owner)
        ServiceRequestFactory(property=prop, tenant=tenant, status="open")
        ServiceRequestFactory(property=prop, tenant=tenant, status="in_progress")
        ServiceRequestFactory(property=prop, tenant=tenant, status="resolved")
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        body = response.json()
        requests = body["data"]["maintenance_requests"]
        assert len(requests) == 2
        assert all(r["id"] is not None for r in requests)
        assert all(r["status"] != "resolved" for r in requests)

    def test_dashboard_empty_state(self, api_client):
        mgmt = _mgmt_user()
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        body = response.json()
        data = body["data"]
        assert data["total_properties"] == 0
        assert data["kpi"]["occupied"]["value"] == 0
        assert data["kpi"]["vacant"]["value"] == 0
        assert data["kpi"]["net_profit"]["value"] == "0.00"
        assert data["kpi"]["payments_received"]["amount"] == "0.00"
        assert data["recent_payments"] == []
        assert data["maintenance_requests"] == []
        assert data["occupancy"]["rate"] == 0

    def test_dashboard_date_is_iso_format(self, api_client):
        mgmt = _mgmt_user()
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        date_str = response.json()["data"]["date"]
        parts = date_str.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4
        assert len(parts[1]) == 2
        assert len(parts[2]) == 2

    def test_dashboard_overdue_shows_attention(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        prop = PropertyFactory(district=district, owner=owner)
        lease = LeaseFactory(property=prop, tenant=tenant)
        PaymentFactory(lease=lease, tenant=tenant, status="overdue")
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        assert response.json()["data"]["payment_status"] == "needs_attention"

    def test_dashboard_no_overdue_shows_good(self, api_client):
        mgmt = _mgmt_user()
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        assert response.json()["data"]["payment_status"] == "good"

    def test_dashboard_on_time_pct(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        prop = PropertyFactory(district=district, owner=owner)
        lease = LeaseFactory(property=prop, tenant=tenant)
        PaymentFactory(lease=lease, tenant=tenant, status="paid")
        PaymentFactory(lease=lease, tenant=tenant, status="paid")
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        pct = response.json()["data"]["kpi"]["payments_received"]["on_time_pct"]
        assert isinstance(pct, int)
        assert 0 <= pct <= 100

    def test_dashboard_net_profit_kpi(self, api_client):
        from datetime import date

        from finance.models import Payment, PayoutSchedule

        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        prop = PropertyFactory(district=district, owner=owner)
        lease = LeaseFactory(property=prop, tenant=tenant)
        agreement = OwnerAgreementFactory(owner=owner, property=prop)
        today = date.today()
        Payment.objects.create(
            lease=lease,
            tenant=tenant,
            paid_by=mgmt,
            amount=200,
            status="paid",
            payment_date=today,
            due_date=today,
        )
        PayoutSchedule.objects.create(
            owner_agreement=agreement,
            owner=owner,
            amount=50,
            status="paid",
            scheduled_date=today,
            paid_date=today,
        )
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        kpi = response.json()["data"]["kpi"]["net_profit"]
        assert kpi["value"] is not None
        assert kpi["change"] is not None

    def test_dashboard_vacant_loss_per_day(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        PropertyFactory(district=district, owner=owner, status="vacant", tenant_charge_price=600)
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(mgmt))
        loss = response.json()["data"]["kpi"]["vacant"]["loss_per_day"]
        assert loss != "0.00"

    def test_dashboard_rbac(self, api_client):
        owner = OwnerFactory()
        response = api_client.get("/api/v1/management/dashboard/", **_make_jwt(owner))
        assert response.status_code == 403

    def test_dashboard_requires_auth(self, api_client):
        response = api_client.get("/api/v1/management/dashboard/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestManagementPnLAPI:
    def test_pnl_returns_all_sections(self, api_client):
        mgmt = _mgmt_user()
        response = api_client.get("/api/v1/management/pnl/", **_make_jwt(mgmt))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "summary" in data
        assert "monthly" in data
        assert "growth" in data
        assert "investor" in data

        s = data["summary"]
        assert "gross_revenue" in s
        assert "owner_payouts" in s
        assert "net_profit" in s
        assert "tax" in s

        inv = data["investor"]
        assert "monthly" in inv
        assert "annual" in inv
        assert "property_count" in inv
        assert "scaled_50" in inv

        growth = data["growth"]
        assert "actual" in growth
        assert "projected" in growth

    def test_pnl_empty_state(self, api_client):
        mgmt = _mgmt_user()
        response = api_client.get("/api/v1/management/pnl/", **_make_jwt(mgmt))
        body = response.json()
        data = body["data"]
        assert data["summary"]["gross_revenue"] == "0.00"
        assert data["summary"]["net_profit"] == "0.00"
        assert all(r["revenue"] == "0.00" for r in data["monthly"])
        assert data["investor"]["property_count"] == 0

    def test_pnl_current_month_summary(self, api_client):
        from datetime import date

        mgmt = _mgmt_user()
        ExchangeRateFactory(currency="USD", rate=12500, effective_date=date.today())
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        prop = PropertyFactory(district=district, owner=owner)
        lease = LeaseFactory(property=prop, tenant=tenant)
        agreement = OwnerAgreementFactory(owner=owner, property=prop)
        today = date.today()
        PaymentFactory(lease=lease, tenant=tenant, status="paid", amount=500, payment_date=today, due_date=today)
        PayoutScheduleFactory(
            owner_agreement=agreement,
            owner=owner,
            amount=200,
            status="paid",
            scheduled_date=today,
            paid_date=today,
        )
        response = api_client.get("/api/v1/management/pnl/", **_make_jwt(mgmt))
        body = response.json()
        summary = body["data"]["summary"]
        assert summary["gross_revenue"] != "0.00"
        assert summary["owner_payouts"] != "0.00"

    def test_pnl_rbac(self, api_client):
        owner = OwnerFactory()
        response = api_client.get("/api/v1/management/pnl/", **_make_jwt(owner))
        assert response.status_code == 403

    def test_pnl_requires_auth(self, api_client):
        response = api_client.get("/api/v1/management/pnl/")
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
class TestManagementUserDetailAPI:
    def test_retrieve_user(self, api_client):
        mgmt = _mgmt_user()
        target = UserFactory(role=UserRole.TENANT, is_active=True)
        response = api_client.get(
            f"/api/v1/management/users/{target.id}/",
            **_make_jwt(mgmt),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["id"] == target.id
        assert body["data"]["role"] == UserRole.TENANT

    def test_retrieve_user_not_found(self, api_client):
        mgmt = _mgmt_user()
        response = api_client.get(
            "/api/v1/management/users/99999/",
            **_make_jwt(mgmt),
        )
        assert response.status_code == 404

    def test_retrieve_user_requires_auth(self, api_client):
        response = api_client.get("/api/v1/management/users/1/")
        assert response.status_code in (401, 403)


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
class TestManagementUserInviteAPI:
    def test_invite_user(self, api_client):
        mgmt = _mgmt_user()
        payload = {
            "first_name": "Nodira",
            "last_name": "Karimova",
            "email": "nodira@example.com",
            "phone": "+998901112233",
            "role": UserRole.OWNER,
        }
        response = api_client.post(
            "/api/v1/management/users/invite/",
            data=json.dumps(payload),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["email"] == "nodira@example.com"
        assert body["data"]["role"] == UserRole.OWNER
        assert body["data"]["username"] == "nodira"
        # The invite returns a one-time temporary password so the user can log in.
        assert body["data"]["temporary_password"]

        from account.models import User

        created = User.objects.get(email="nodira@example.com")
        # Invited users get a usable temporary password and must change it on first login.
        assert created.has_usable_password() is True
        assert created.must_change_password is True
        assert created.check_password(body["data"]["temporary_password"]) is True

    def test_invite_user_unique_username(self, api_client):
        mgmt = _mgmt_user()
        UserFactory(username="dupe")
        payload = {
            "first_name": "Test",
            "email": "dupe@company.com",
            "role": UserRole.TENANT,
        }
        response = api_client.post(
            "/api/v1/management/users/invite/",
            data=json.dumps(payload),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert response.status_code == 201
        assert response.json()["data"]["username"] == "dupe1"

    def test_invite_user_invalid_role(self, api_client):
        mgmt = _mgmt_user()
        payload = {
            "first_name": "Test",
            "email": "badrole@example.com",
            "role": "superhero",
        }
        response = api_client.post(
            "/api/v1/management/users/invite/",
            data=json.dumps(payload),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert response.status_code == 400
        assert response.json()["success"] is False

    def test_invite_user_rbac(self, api_client):
        owner = OwnerFactory()
        payload = {"first_name": "Test", "email": "x@example.com", "role": UserRole.TENANT}
        response = api_client.post(
            "/api/v1/management/users/invite/",
            data=json.dumps(payload),
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 403

    def test_invite_user_requires_auth(self, api_client):
        payload = {"first_name": "Test", "email": "x@example.com", "role": UserRole.TENANT}
        response = api_client.post(
            "/api/v1/management/users/invite/",
            data=json.dumps(payload),
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

    def test_list_leases_search_by_tenant_name(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory(first_name="Zamira")
        other = TenantFactory(first_name="Bakhtiyor")
        prop = PropertyFactory(owner=owner, district=district)
        LeaseFactory(property=prop, tenant=tenant)
        LeaseFactory(property=prop, tenant=other)
        response = api_client.get("/api/v1/management/leases/?search=Zamira", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["tenant_name"].startswith("Zamira")

    def test_list_leases_ends_within(self, api_client):
        from datetime import date, timedelta

        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        prop = PropertyFactory(owner=owner, district=district)
        soon = LeaseFactory(property=prop, tenant=tenant, end_date=date.today() + timedelta(days=10))
        LeaseFactory(property=prop, tenant=tenant, end_date=date.today() + timedelta(days=200))
        response = api_client.get("/api/v1/management/leases/?ends_within=30", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        ids = [ls["id"] for ls in data]
        assert soon.id in ids
        assert len(data) == 1


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

    def test_list_agreements_search_by_number(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        OwnerAgreementFactory(owner=owner, property=prop, agreement_number="AG-FINDME-1")
        OwnerAgreementFactory(owner=owner, property=prop, agreement_number="AG-OTHER-2")
        response = api_client.get("/api/v1/management/owner-agreements/?search=FINDME", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["agreement_number"] == "AG-FINDME-1"

    def test_list_agreements_ends_within(self, api_client):
        from datetime import date, timedelta

        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        soon = OwnerAgreementFactory(owner=owner, property=prop, end_date=date.today() + timedelta(days=5))
        OwnerAgreementFactory(owner=owner, property=prop, end_date=date.today() + timedelta(days=365))
        response = api_client.get("/api/v1/management/owner-agreements/?ends_within=30", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        ids = [a["id"] for a in data]
        assert soon.id in ids
        assert len(data) == 1


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

    def test_list_payments_search_by_tenant(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory(first_name="Zamira", last_name="Karimova")
        other = TenantFactory(first_name="Bek", last_name="Aliyev")
        paid_by = UserFactory()
        prop = PropertyFactory(owner=owner, district=district)
        lease = LeaseFactory(property=prop, tenant=tenant)
        lease2 = LeaseFactory(property=prop, tenant=other)
        PaymentFactory(lease=lease, tenant=tenant, paid_by=paid_by)
        PaymentFactory(lease=lease2, tenant=other, paid_by=paid_by)
        response = api_client.get("/api/v1/management/payments/?search=Zamira", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert all("Zamira" in p["tenant_name"] for p in data)
        assert len(data) == 1

    def test_list_payments_filter_by_property(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        paid_by = UserFactory()
        prop_a = PropertyFactory(owner=owner, district=district)
        prop_b = PropertyFactory(owner=owner, district=district)
        lease_a = LeaseFactory(property=prop_a, tenant=tenant)
        lease_b = LeaseFactory(property=prop_b, tenant=tenant)
        PaymentFactory(lease=lease_a, tenant=tenant, paid_by=paid_by)
        PaymentFactory(lease=lease_b, tenant=tenant, paid_by=paid_by)
        response = api_client.get(f"/api/v1/management/payments/?property_id={prop_a.id}", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(p["property_id"] == prop_a.id for p in data)
        assert len(data) == 1

    def test_list_payments_overdue_derived(self, api_client):
        from datetime import date

        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        paid_by = UserFactory()
        prop = PropertyFactory(owner=owner, district=district)
        lease = LeaseFactory(property=prop, tenant=tenant)
        # A pending payment past its due date is "overdue" even without the flag.
        past = PaymentFactory(
            lease=lease, tenant=tenant, paid_by=paid_by, status="pending", due_date=date.today() - timedelta(days=5)
        )
        PaymentFactory(
            lease=lease, tenant=tenant, paid_by=paid_by, status="pending", due_date=date.today() + timedelta(days=5)
        )
        response = api_client.get("/api/v1/management/payments/?overdue=true", **_make_jwt(mgmt))
        assert response.status_code == 200
        ids = [p["id"] for p in response.json()["data"]]
        assert past.id in ids
        assert len(ids) == 1

    def test_list_payments_due_range(self, api_client):
        from datetime import date

        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        paid_by = UserFactory()
        prop = PropertyFactory(owner=owner, district=district)
        lease = LeaseFactory(property=prop, tenant=tenant)
        inside = PaymentFactory(lease=lease, tenant=tenant, paid_by=paid_by, due_date=date(2026, 6, 15))
        PaymentFactory(lease=lease, tenant=tenant, paid_by=paid_by, due_date=date(2026, 8, 1))
        response = api_client.get(
            "/api/v1/management/payments/?due_from=2026-06-01&due_to=2026-06-30", **_make_jwt(mgmt)
        )
        assert response.status_code == 200
        ids = [p["id"] for p in response.json()["data"]]
        assert inside.id in ids
        assert len(ids) == 1

    def test_list_payments_order_by_due_date(self, api_client):
        from datetime import date

        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        paid_by = UserFactory()
        prop = PropertyFactory(owner=owner, district=district)
        lease = LeaseFactory(property=prop, tenant=tenant)
        later = PaymentFactory(lease=lease, tenant=tenant, paid_by=paid_by, due_date=date(2026, 9, 1))
        earlier = PaymentFactory(lease=lease, tenant=tenant, paid_by=paid_by, due_date=date(2026, 6, 1))
        response = api_client.get("/api/v1/management/payments/?order=due_date", **_make_jwt(mgmt))
        assert response.status_code == 200
        ids = [p["id"] for p in response.json()["data"]]
        assert ids.index(earlier.id) < ids.index(later.id)

    def test_payments_stats(self, api_client):
        from datetime import date

        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        tenant = TenantFactory()
        paid_by = UserFactory()
        prop = PropertyFactory(owner=owner, district=district)
        lease = LeaseFactory(property=prop, tenant=tenant)
        today = date.today()
        PaymentFactory(
            lease=lease,
            tenant=tenant,
            paid_by=paid_by,
            status="paid",
            currency="USD",
            amount=1000,
            payment_date=today.replace(day=1),
        )
        PaymentFactory(
            lease=lease,
            tenant=tenant,
            paid_by=paid_by,
            status="overdue",
            currency="USD",
            amount=200,
            due_date=today - timedelta(days=3),
        )
        response = api_client.get("/api/v1/management/payments/stats/", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert "collected_month" in data
        assert "outstanding" in data
        assert "overdue_total" in data
        assert data["counts"]["overdue"] >= 1

    def test_payments_stats_rbac(self, api_client):
        owner = OwnerFactory()
        response = api_client.get("/api/v1/management/payments/stats/", **_make_jwt(owner))
        assert response.status_code == 403

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

    def test_list_payouts_search_by_owner(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory(first_name="Sanjar", last_name="Tursunov")
        other = OwnerFactory(first_name="Dilnoza", last_name="Yusupova")
        prop = PropertyFactory(owner=owner, district=district)
        prop2 = PropertyFactory(owner=other, district=district)
        agreement = OwnerAgreementFactory(owner=owner, property=prop)
        agreement2 = OwnerAgreementFactory(owner=other, property=prop2)
        PayoutScheduleFactory(owner_agreement=agreement, owner=owner)
        PayoutScheduleFactory(owner_agreement=agreement2, owner=other)
        response = api_client.get("/api/v1/management/payouts/?search=Sanjar", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert all("Sanjar" in p["owner_name"] for p in data)
        assert len(data) == 1

    def test_list_payouts_scheduled_range(self, api_client):
        from datetime import date

        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        agreement = OwnerAgreementFactory(owner=owner, property=prop)
        inside = PayoutScheduleFactory(owner_agreement=agreement, owner=owner, scheduled_date=date(2026, 7, 25))
        PayoutScheduleFactory(owner_agreement=agreement, owner=owner, scheduled_date=date(2026, 9, 25))
        response = api_client.get(
            "/api/v1/management/payouts/?scheduled_from=2026-07-01&scheduled_to=2026-07-31", **_make_jwt(mgmt)
        )
        assert response.status_code == 200
        ids = [p["id"] for p in response.json()["data"]]
        assert inside.id in ids
        assert len(ids) == 1

    def test_payouts_stats(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, district=district)
        agreement = OwnerAgreementFactory(owner=owner, property=prop)
        PayoutScheduleFactory(owner_agreement=agreement, owner=owner, status="held", currency="USD", amount=500)
        response = api_client.get("/api/v1/management/payouts/stats/", **_make_jwt(mgmt))
        assert response.status_code == 200
        data = response.json()["data"]
        assert "next_run_date" in data
        assert "held_total" in data
        assert data["counts"]["held"] >= 1

    def test_payouts_stats_rbac(self, api_client):
        tenant = TenantFactory()
        response = api_client.get("/api/v1/management/payouts/stats/", **_make_jwt(tenant))
        assert response.status_code == 403

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
