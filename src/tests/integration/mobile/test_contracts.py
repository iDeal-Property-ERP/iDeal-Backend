from datetime import date
from decimal import Decimal

import pytest

from core.constants import LeaseStatus
from tests.factories import LeaseFactory, OwnerAgreementFactory, PropertyFactory, TenantFactory
from tests.integration.property.test_api import _make_jwt

pytestmark = pytest.mark.django_db

CONTRACTS_URL = "/api/v1/mobile/contracts/"


def _lease_for(tenant, *, start_date: date, end_date: date):
    property_obj = PropertyFactory(name="Tenant contract home", address="12 Amir Temur Street")
    agreement = OwnerAgreementFactory(property=property_obj, owner=property_obj.owner, currency="USD")
    return LeaseFactory(
        property=property_obj,
        owner_agreement=agreement,
        tenant=tenant,
        start_date=start_date,
        end_date=end_date,
        monthly_rent=Decimal("850.00"),
        status=LeaseStatus.ACTIVE,
    )


class TestMobileContracts:
    def test_requires_authentication(self, api_client):
        response = api_client.get(CONTRACTS_URL)

        assert response.status_code == 401

    def test_lists_only_current_tenant_leases_with_contract_card_data(self, api_client):
        tenant = TenantFactory()
        other_tenant = TenantFactory()
        lease = _lease_for(tenant, start_date=date(2026, 2, 1), end_date=date(2027, 2, 1))
        _lease_for(other_tenant, start_date=date(2026, 3, 1), end_date=date(2027, 3, 1))

        response = api_client.get(CONTRACTS_URL, **_make_jwt(tenant))

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "message": "OK",
            "data": [
                {
                    "id": lease.id,
                    "reference": f"#{lease.id}",
                    "property": {
                        "id": lease.property_id,
                        "title": "Tenant contract home",
                        "address": "12 Amir Temur Street",
                    },
                    "start_date": "2026-02-01",
                    "end_date": "2027-02-01",
                    "monthly_rent": "850.00",
                    "currency": "USD",
                    "status": LeaseStatus.ACTIVE,
                    "status_display": str(lease.get_status_display()),
                    "document_url": None,
                }
            ],
        }
