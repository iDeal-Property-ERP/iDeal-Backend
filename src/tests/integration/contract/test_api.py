import json

import pytest
from django.conf import settings

from tests.factories import LeaseFactory, OwnerAgreementFactory


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
class TestOwnerAgreementAPI:
    def test_create_owner_agreement(self, api_client, management, owner, property_obj):
        payload = json.dumps(
            {
                "owner_id": owner.id,
                "property_id": property_obj.id,
                "agreement_number": "AG-TEST-001",
                "signed_date": "2026-01-01",
                "start_date": "2026-01-01",
                "end_date": "2027-01-01",
                "commission_rate": "15.00",
            }
        )
        response = api_client.post(
            "/api/v1/contracts/owner-agreements/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["agreement_number"] == "AG-TEST-001"
        assert body["data"]["status"] == "active"

    def test_create_owner_agreement_requires_auth(self, api_client, owner, property_obj):
        payload = json.dumps(
            {
                "owner_id": owner.id,
                "property_id": property_obj.id,
                "agreement_number": "AG-TEST-002",
                "signed_date": "2026-01-01",
                "start_date": "2026-01-01",
                "end_date": "2027-01-01",
                "commission_rate": "15.00",
            }
        )
        response = api_client.post(
            "/api/v1/contracts/owner-agreements/",
            payload,
            content_type="application/json",
        )
        assert response.status_code in (401, 403)

    def test_list_owner_agreements(self, api_client, management, owner):
        OwnerAgreementFactory(owner=owner)
        OwnerAgreementFactory(owner=owner)
        response = api_client.get(
            "/api/v1/contracts/owner-agreements/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) == 2

    def test_retrieve_owner_agreement(self, api_client, management, owner):
        agreement = OwnerAgreementFactory(owner=owner)
        response = api_client.get(
            f"/api/v1/contracts/owner-agreements/{agreement.id}/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["id"] == agreement.id
        assert body["data"]["agreement_number"] == agreement.agreement_number

    def test_retrieve_owner_agreement_404(self, api_client, management):
        response = api_client.get(
            "/api/v1/contracts/owner-agreements/99999/",
            **_make_jwt(management),
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestLeaseAPI:
    def test_create_lease_property_status_rented(self, api_client, management, tenant, property_obj):
        agreement = OwnerAgreementFactory(property=property_obj)
        property_obj.status = "vacant"
        property_obj.save()

        payload = json.dumps(
            {
                "property_id": property_obj.id,
                "owner_agreement_id": agreement.id,
                "tenant_id": tenant.id,
                "start_date": "2026-06-01",
                "end_date": "2027-06-01",
                "monthly_rent": "600.00",
                "deposit": "600.00",
            }
        )
        response = api_client.post(
            "/api/v1/contracts/leases/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "active"

        property_obj.refresh_from_db()
        assert property_obj.status == "rented"

    def test_create_lease_requires_auth(self, api_client, tenant, property_obj):
        agreement = OwnerAgreementFactory(property=property_obj)
        payload = json.dumps(
            {
                "property_id": property_obj.id,
                "owner_agreement_id": agreement.id,
                "tenant_id": tenant.id,
                "start_date": "2026-06-01",
                "end_date": "2027-06-01",
                "monthly_rent": "600.00",
                "deposit": "600.00",
            }
        )
        response = api_client.post(
            "/api/v1/contracts/leases/",
            payload,
            content_type="application/json",
        )
        assert response.status_code in (401, 403)

    def test_list_leases(self, api_client, management):
        LeaseFactory()
        LeaseFactory()
        response = api_client.get(
            "/api/v1/contracts/leases/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 2

    def test_retrieve_lease(self, api_client, management):
        lease = LeaseFactory()
        response = api_client.get(
            f"/api/v1/contracts/leases/{lease.id}/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["id"] == lease.id

    def test_retrieve_lease_404(self, api_client, management):
        response = api_client.get(
            "/api/v1/contracts/leases/99999/",
            **_make_jwt(management),
        )
        assert response.status_code == 404

    def test_partial_update_lease(self, api_client, management):
        lease = LeaseFactory(monthly_rent="600.00", status="active")
        payload = json.dumps({"monthly_rent": "750.00", "status": "renewed"})
        response = api_client.patch(
            f"/api/v1/contracts/leases/{lease.id}/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["monthly_rent"] == "750.00"
        assert body["data"]["status"] == "renewed"

        lease.refresh_from_db()
        assert str(lease.monthly_rent) == "750.00"

    def test_partial_update_lease_requires_auth(self, api_client):
        lease = LeaseFactory()
        payload = json.dumps({"monthly_rent": "750.00"})
        response = api_client.patch(
            f"/api/v1/contracts/leases/{lease.id}/",
            payload,
            content_type="application/json",
        )
        assert response.status_code in (401, 403)

    def test_invalid_lease_data(self, api_client, management):
        payload = json.dumps({"property_id": 1})
        response = api_client.post(
            "/api/v1/contracts/leases/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert "error" in body


@pytest.mark.django_db
class TestLeaseRenewAPI:
    def test_renew_lease(self, api_client, management, owner, property_obj, tenant):
        agreement = OwnerAgreementFactory(property=property_obj)
        lease = LeaseFactory(
            property=property_obj,
            owner_agreement=agreement,
            tenant=tenant,
            status="active",
            monthly_rent=500.00,
        )

        payload = json.dumps(
            {
                "new_start_date": "2027-07-01",
                "new_end_date": "2028-07-01",
                "new_monthly_rent": "600.00",
            }
        )
        response = api_client.post(
            f"/api/v1/contracts/leases/{lease.id}/renew/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["monthly_rent"] == "600.00"
        assert body["data"]["status"] == "active"
        assert body["data"]["id"] != lease.id

        lease.refresh_from_db()
        assert lease.status == "renewed"

    def test_renew_lease_requires_auth(self, api_client):
        lease = LeaseFactory()
        payload = json.dumps(
            {
                "new_start_date": "2027-07-01",
                "new_end_date": "2028-07-01",
                "new_monthly_rent": "600.00",
            }
        )
        response = api_client.post(
            f"/api/v1/contracts/leases/{lease.id}/renew/",
            payload,
            content_type="application/json",
        )
        assert response.status_code in (401, 403)

    def test_renew_lease_404(self, api_client, management):
        payload = json.dumps(
            {
                "new_start_date": "2027-07-01",
                "new_end_date": "2028-07-01",
                "new_monthly_rent": "600.00",
            }
        )
        response = api_client.post(
            "/api/v1/contracts/leases/99999/renew/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 404
