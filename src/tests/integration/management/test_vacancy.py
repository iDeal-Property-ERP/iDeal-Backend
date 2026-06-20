from decimal import Decimal

import pytest

from core.constants import PropertyStatus
from tests.factories import OwnerFactory, PropertyFactory, UserFactory
from tests.integration.property.test_api import _make_jwt


@pytest.mark.django_db
class TestVacancyReport:
    def test_vacancy_report(self, api_client):
        mgmt = UserFactory()
        owner = OwnerFactory()
        PropertyFactory(
            owner=owner,
            status=PropertyStatus.VACANT,
            tenant_charge_price=Decimal("600.00"),
            vacant_days=10,
        )
        PropertyFactory(owner=owner, status=PropertyStatus.RENTED)

        response = api_client.get("/api/v1/management/vacancy/", **_make_jwt(mgmt))

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["vacant_count"] == 1
        assert len(data["properties"]) == 1
        row = data["properties"][0]
        assert row["daily_loss"] == "20.00"
        assert row["accrued_loss"] == "200.00"

    def test_vacancy_rbac(self, api_client):
        owner = OwnerFactory()
        response = api_client.get("/api/v1/management/vacancy/", **_make_jwt(owner))
        assert response.status_code == 403
