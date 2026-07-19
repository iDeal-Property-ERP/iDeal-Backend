"""Deferred Management-module features: maintenance SLA/phone, assignees,
property tenant/vacancy enrichment, agreement amounts, CSV property import."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.constants import LeaseStatus, PropertyStatus, ServiceRequestPriority, UserRole
from tests.factories import (
    DistrictFactory,
    LeaseFactory,
    OwnerAgreementFactory,
    OwnerFactory,
    PropertyFactory,
    ServiceRequestFactory,
    TenantFactory,
    UserFactory,
)
from tests.integration.property.test_api import _make_jwt


def _mgmt_user():
    return UserFactory(role=UserRole.MANAGEMENT)


@pytest.mark.django_db
class TestServiceRequestSlaAndPhone:
    def test_tenant_phone_and_sla_fields(self, api_client):
        mgmt = _mgmt_user()
        tenant = TenantFactory(phone="+998901234567")
        ServiceRequestFactory(tenant=tenant, priority=ServiceRequestPriority.CRITICAL)

        response = api_client.get("/api/v1/management/service-requests/", **_make_jwt(mgmt))
        assert response.status_code == 200
        row = response.json()["data"][0]
        assert row["tenant_phone"] == "+998901234567"
        assert row["sla_hours"] == 4
        assert row["sla_due_at"] is not None
        assert row["sla_breached"] is False

    def test_sla_breached_for_old_open_request(self, api_client):
        mgmt = _mgmt_user()
        sr = ServiceRequestFactory(priority=ServiceRequestPriority.HIGH)
        type(sr).objects.filter(pk=sr.pk).update(created_at=timezone.now() - timedelta(hours=48))

        response = api_client.get("/api/v1/management/service-requests/", **_make_jwt(mgmt))
        row = response.json()["data"][0]
        assert row["sla_hours"] == 8
        assert row["sla_breached"] is True

    def test_sla_not_breached_when_resolved(self, api_client):
        from core.constants import ServiceRequestStatus

        mgmt = _mgmt_user()
        sr = ServiceRequestFactory(
            priority=ServiceRequestPriority.LOW,
            status=ServiceRequestStatus.RESOLVED,
            resolved_at=timezone.now(),
        )
        type(sr).objects.filter(pk=sr.pk).update(created_at=timezone.now() - timedelta(days=30))

        response = api_client.get("/api/v1/management/service-requests/", **_make_jwt(mgmt))
        row = response.json()["data"][0]
        assert row["sla_breached"] is False


@pytest.mark.django_db
class TestAssigneesEndpoint:
    def test_lists_active_management_users(self, api_client):
        mgmt = UserFactory(role=UserRole.MANAGEMENT, first_name="Ann", last_name="Lee")
        UserFactory(role=UserRole.MANAGEMENT, is_active=False)
        TenantFactory()

        response = api_client.get("/api/v1/management/assignees/", **_make_jwt(mgmt))
        assert response.status_code == 200
        rows = response.json()["data"]
        ids = [r["id"] for r in rows]
        assert mgmt.id in ids
        assert all(set(r) == {"id", "full_name"} for r in rows)
        assert {"id": mgmt.id, "full_name": "Ann Lee"} in rows
        # Inactive and non-management users are excluded.
        assert len(rows) == 1


@pytest.mark.django_db
class TestPropertyTenantVacancyFields:
    def test_rented_property_has_tenant_fields(self, api_client):
        mgmt = _mgmt_user()
        prop = PropertyFactory(status=PropertyStatus.RENTED)
        tenant = TenantFactory(first_name="Tim", last_name="Berners")
        lease = LeaseFactory(property=prop, tenant=tenant, status=LeaseStatus.ACTIVE, start_date=date(2026, 1, 15))

        response = api_client.get("/api/v1/management/properties/", **_make_jwt(mgmt))
        row = next(r for r in response.json()["data"] if r["id"] == prop.id)
        assert row["tenant_name"] == "Tim Berners"
        assert row["tenant_since"] == lease.start_date.isoformat()
        assert row["vacant_days"] is None
        assert row["vacancy_loss_per_day"] is None

    def test_vacant_property_recomputes_days_and_loss(self, api_client):
        mgmt = _mgmt_user()
        prop = PropertyFactory(
            status=PropertyStatus.VACANT,
            vacant_since=date.today() - timedelta(days=10),
            vacant_days=3,  # stale stored counter must be ignored
            owner_guaranteed_price=Decimal("450.00"),
        )

        response = api_client.get("/api/v1/management/properties/", **_make_jwt(mgmt))
        row = next(r for r in response.json()["data"] if r["id"] == prop.id)
        assert row["tenant_name"] is None
        assert row["tenant_since"] is None
        assert row["vacant_days"] == 10
        assert row["vacancy_loss_per_day"] == "15.00"  # 450 / 30


@pytest.mark.django_db
class TestAgreementAmounts:
    def test_output_includes_amounts_and_margin(self, api_client):
        mgmt = _mgmt_user()
        OwnerAgreementFactory(owner_guaranteed_amount=Decimal("450.00"), tenant_charge_amount=Decimal("550.00"))
        OwnerAgreementFactory(owner_guaranteed_amount=None, tenant_charge_amount=None)

        response = api_client.get("/api/v1/management/owner-agreements/", **_make_jwt(mgmt))
        rows = response.json()["data"]
        with_amounts = next(r for r in rows if r["owner_guaranteed_amount"] is not None)
        assert with_amounts["owner_guaranteed_amount"] == "450.00"
        assert with_amounts["tenant_charge_amount"] == "550.00"
        assert with_amounts["margin"] == "100.00"
        without = next(r for r in rows if r["owner_guaranteed_amount"] is None)
        assert without["margin"] is None

    def test_onboarding_approve_snapshots_property_prices(self):
        from tests.factories import OwnerOnboardingFactory

        onboarding = OwnerOnboardingFactory(
            property=PropertyFactory(
                status=PropertyStatus.PENDING_REVIEW,
                owner_guaranteed_price=Decimal("400.00"),
                tenant_charge_price=Decimal("500.00"),
            )
        )
        agreement = onboarding.approve(
            reviewed_by=_mgmt_user(),
            commission_rate=Decimal("10.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
        )
        assert agreement.owner_guaranteed_amount == Decimal("400.00")
        assert agreement.tenant_charge_amount == Decimal("500.00")


@pytest.mark.django_db
class TestPropertyCsvImport:
    def test_import_reports_created_and_errors(self, api_client):
        mgmt = _mgmt_user()
        district = DistrictFactory()
        owner = OwnerFactory()
        csv_text = (
            "name,address,district_id,rooms,area_sqm,floor,total_floors,owner_id,"
            "ask_price,owner_guaranteed_price,tenant_charge_price\n"
            f"Imported One,12 Amir Temur,{district.id},2,55,3,5,{owner.id},500,450,550\n"
            f"Broken Row,13 Amir Temur,999999,2,55,3,5,{owner.id},500,450,550\n"
        )
        upload = SimpleUploadedFile("props.csv", csv_text.encode(), content_type="text/csv")

        response = api_client.post("/api/v1/management/properties/import/", {"file": upload}, **_make_jwt(mgmt))
        assert response.status_code in (200, 201)
        data = response.json()["data"]
        assert data["created"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["row"] == 3
        assert "district" in data["errors"][0]["message"]

        from property.models import Property

        prop = Property.objects.get(name="Imported One")
        assert prop.district_id == district.id
        assert prop.owner_id == owner.id
        assert str(prop.tenant_charge_price) == "550.00"

    def test_import_requires_a_file_or_text(self, api_client):
        mgmt = _mgmt_user()
        response = api_client.post("/api/v1/management/properties/import/", **_make_jwt(mgmt))
        assert response.status_code == 400
