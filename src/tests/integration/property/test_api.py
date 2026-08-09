import json

import pytest
from django.conf import settings
from property.models import Property

from tests.factories import DistrictFactory, PropertyFactory


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


def _create_payload(district, owner, **overrides):
    data = {
        "name": "Test Property",
        "address": "123 Test St",
        "district_id": district.id,
        "rooms": 2,
        "area_sqm": 70,
        "floor": 5,
        "total_floors": 10,
        "owner_id": owner.id,
        "ask_price": "450.00",
        "owner_guaranteed_price": "400.00",
        "tenant_charge_price": "500.00",
    }
    data.update(overrides)
    return json.dumps(data)


@pytest.mark.django_db
class TestPropertyCreate:
    def test_create_property(self, api_client, management, owner):
        district = DistrictFactory()
        response = api_client.post(
            "/api/v1/properties/",
            _create_payload(district, owner),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["name"] == "Test Property"
        assert body["data"]["status"] == "vacant"

    def test_create_property_requires_auth(self, api_client, owner):
        district = DistrictFactory()
        response = api_client.post(
            "/api/v1/properties/",
            _create_payload(district, owner),
            content_type="application/json",
        )
        assert response.status_code in (401, 403)

    def test_create_property_invalid_data(self, api_client, management):
        payload = json.dumps({"name": "No Required Fields"})
        response = api_client.post(
            "/api/v1/properties/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert "error" in body

    def test_create_property_nonexistent_district(self, api_client, management, owner):
        district = DistrictFactory()
        response = api_client.post(
            "/api/v1/properties/",
            _create_payload(district, owner, district_id=99999),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert any("district_id" in str(e.get("loc", [])) for e in body.get("error", []))

    def test_create_property_nonexistent_owner(self, api_client, management, owner):
        district = DistrictFactory()
        response = api_client.post(
            "/api/v1/properties/",
            _create_payload(district, owner, owner_id=99999),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert any("owner_id" in str(e.get("loc", [])) for e in body.get("error", []))


@pytest.mark.django_db
class TestPropertyList:
    def test_list_properties(self, api_client, owner):
        district = DistrictFactory()
        PropertyFactory(district=district, owner=owner, name="P1")
        PropertyFactory(district=district, owner=owner, name="P2")
        response = api_client.get("/api/v1/properties/", **_make_jwt(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 2


@pytest.mark.django_db
class TestPropertyRetrieve:
    def test_retrieve_property(self, api_client, property_obj):
        owner = property_obj.owner
        response = api_client.get(
            f"/api/v1/properties/{property_obj.id}/",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["id"] == property_obj.id
        assert body["data"]["district"]["id"] == property_obj.district.id
        assert body["data"]["owner"]["id"] == owner.id

    def test_retrieve_404(self, api_client, owner):
        response = api_client.get("/api/v1/properties/99999/", **_make_jwt(owner))
        assert response.status_code == 404


@pytest.mark.django_db
class TestPropertyUpdate:
    def test_partial_update_property(self, api_client, management, property_obj):
        payload = json.dumps({"name": "New Name", "status": "maintenance"})
        response = api_client.patch(
            f"/api/v1/properties/{property_obj.id}/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["name"] == "New Name"
        assert body["data"]["status"] == "maintenance"

    def test_partial_update_nonexistent_district(self, api_client, management, property_obj):
        payload = json.dumps({"district_id": 99999})
        response = api_client.patch(
            f"/api/v1/properties/{property_obj.id}/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert any("district_id" in str(e.get("loc", [])) for e in body.get("error", []))

    def test_partial_update_nonexistent_owner(self, api_client, management, property_obj):
        payload = json.dumps({"owner_id": 99999})
        response = api_client.patch(
            f"/api/v1/properties/{property_obj.id}/",
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert any("owner_id" in str(e.get("loc", [])) for e in body.get("error", []))

    def test_partial_update_rejects_floor_above_persisted_total_floors(self, api_client, management, property_obj):
        property_obj.total_floors = 5
        property_obj.floor = 1
        property_obj.save(update_fields=["total_floors", "floor"])

        response = api_client.patch(
            f"/api/v1/properties/{property_obj.id}/",
            json.dumps({"floor": 7}),
            content_type="application/json",
            **_make_jwt(management),
        )

        assert response.status_code == 400
        assert response.json()["success"] is False
        property_obj.refresh_from_db()
        assert property_obj.floor == 1


@pytest.mark.django_db
class TestPropertyDelete:
    def test_delete_property(self, api_client, management, property_obj):
        response = api_client.delete(
            f"/api/v1/properties/{property_obj.id}/",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["deleted"] is True
        assert not Property.objects.filter(id=property_obj.id).exists()

    def test_archive_property_with_contract_history(self, api_client, management, property_obj):
        from tests.factories.contract import LeaseFactory, OwnerAgreementFactory

        agreement = OwnerAgreementFactory(property=property_obj)
        lease = LeaseFactory(property=property_obj, owner_agreement=agreement)

        response = api_client.delete(
            f"/api/v1/properties/{property_obj.id}/",
            **_make_jwt(management),
        )

        assert response.status_code == 200
        assert response.json()["data"]["deleted"] is True
        assert Property.deleted_objects.filter(id=property_obj.id).exists()
        assert agreement.__class__.objects.filter(id=agreement.id).exists()
        assert lease.__class__.objects.filter(id=lease.id).exists()


@pytest.mark.django_db
class TestPropertyPagination:
    def test_list_pagination(self, api_client, management):
        district = DistrictFactory()
        owner = PropertyFactory().owner
        for i in range(25):
            PropertyFactory(district=district, owner=owner, name=f"P{i}")
        response = api_client.get(
            "/api/v1/properties/?page=2&per_page=10",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "count" in data
        assert "page" in data
        assert data["per_page"] == 10
        assert "object_list" in data["page"]


@pytest.mark.django_db
class TestPropertyNestedOutput:
    def test_nested_district_output(self, api_client, property_obj):
        owner = property_obj.owner
        response = api_client.get(
            f"/api/v1/properties/{property_obj.id}/",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["district"]["name"] == property_obj.district.name
        assert data["district"]["city"] == "Toshkent"
        assert data["owner"]["first_name"] == owner.first_name
