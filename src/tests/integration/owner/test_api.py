import pytest

from tests.factories import DistrictFactory, OwnerFactory, PropertyFactory


@pytest.mark.django_db
class TestOwnerPropertiesAPI:
    def test_owner_sees_own_properties(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()
        PropertyFactory(owner=owner, district=district, name="My Property")
        other_owner = OwnerFactory()
        PropertyFactory(owner=other_owner, district=district, name="Not Mine")
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/properties/", **_make_jwt(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        names = [p["name"] for p in body["data"]]
        assert "My Property" in names
        assert "Not Mine" not in names

    def test_owner_properties_rbac(self, api_client):
        from tests.factories import TenantFactory

        tenant = TenantFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/properties/", **_make_jwt(tenant))
        assert response.status_code == 403

    def test_owner_properties_requires_auth(self, api_client):
        response = api_client.get("/api/v1/owner/properties/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestOwnerEarningsAPI:
    def test_owner_earnings(self, api_client):
        owner = OwnerFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/earnings/", **_make_jwt(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "total_guaranteed" in data
        assert "total_paid" in data
        assert "total_pending" in data
        assert data["currency"] == "USD"

    def test_owner_earnings_rbac(self, api_client):
        from tests.factories import TenantFactory

        tenant = TenantFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/earnings/", **_make_jwt(tenant))
        assert response.status_code == 403


@pytest.mark.django_db
class TestOwnerWhyAPI:
    def test_owner_why(self, api_client):
        owner = OwnerFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/why/", **_make_jwt(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "title" in data
        assert "description" in data
        assert "benefits" in data
        assert isinstance(data["benefits"], list)

    def test_owner_why_rbac(self, api_client):
        from tests.factories import TenantFactory

        tenant = TenantFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/why/", **_make_jwt(tenant))
        assert response.status_code == 403

    def test_owner_why_requires_auth(self, api_client):
        response = api_client.get("/api/v1/owner/why/")
        assert response.status_code == 401
