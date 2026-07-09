from datetime import UTC, date, datetime, timedelta

import jwt
import pytest
from django.conf import settings

from core.constants import LeaseStatus, PropertyStatus, UserRole
from tests.factories import (
    DistrictFactory,
    LeaseFactory,
    PropertyFactory,
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


def _mgmt():
    return UserFactory(role=UserRole.MANAGEMENT)


def _geo(**kwargs):
    kwargs.setdefault("map_lat", "41.3111000")
    kwargs.setdefault("map_lon", "69.2797000")
    return PropertyFactory(**kwargs)


@pytest.mark.django_db
class TestPortfolioMap:
    def test_returns_only_geocoded_properties(self, api_client):
        _geo()
        PropertyFactory()  # no coordinates
        resp = api_client.get("/api/v1/management/properties/map/", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["map_lat"] is not None
        assert rows[0]["map_lon"] is not None

    def test_includes_all_statuses_unlike_marketplace_map(self, api_client):
        for status in (PropertyStatus.RENTED, PropertyStatus.VACANT, PropertyStatus.MAINTENANCE):
            _geo(status=status)
        resp = api_client.get("/api/v1/management/properties/map/", **_make_jwt(_mgmt()))
        assert {r["status"] for r in resp.json()["data"]} == {
            PropertyStatus.RENTED,
            PropertyStatus.VACANT,
            PropertyStatus.MAINTENANCE,
        }

    def test_filters(self, api_client):
        district = DistrictFactory(name="Chilonzor")
        _geo(status=PropertyStatus.RENTED, district=district, rooms=3, tenant_charge_price=650)
        _geo(status=PropertyStatus.VACANT, rooms=1, tenant_charge_price=300)
        headers = _make_jwt(_mgmt())

        assert len(api_client.get("/api/v1/management/properties/map/?status=rented", **headers).json()["data"]) == 1
        assert (
            len(
                api_client.get(f"/api/v1/management/properties/map/?district_id={district.id}", **headers).json()[
                    "data"
                ]
            )
            == 1
        )
        assert len(api_client.get("/api/v1/management/properties/map/?rooms=3", **headers).json()["data"]) == 1
        assert len(api_client.get("/api/v1/management/properties/map/?price_min=500", **headers).json()["data"]) == 1

    def test_search(self, api_client):
        _geo(name="Chilonzor Park View 7")
        _geo(name="Sergeli New Build 3-14")
        resp = api_client.get("/api/v1/management/properties/map/?search=chilonzor", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["name"] == "Chilonzor Park View 7"

    def test_bbox(self, api_client):
        _geo(map_lat="41.3111000", map_lon="69.2797000")  # inside
        _geo(map_lat="41.5000000", map_lon="70.0000000")  # outside
        resp = api_client.get("/api/v1/management/properties/map/?bbox=69.0,41.0,69.5,41.4", **_make_jwt(_mgmt()))
        assert len(resp.json()["data"]) == 1

    def test_active_lease_enrichment(self, api_client):
        rented = _geo(status=PropertyStatus.RENTED)
        tenant = TenantFactory(first_name="Viktoriya", last_name="Kim")
        lease = LeaseFactory(
            property=rented, tenant=tenant, status=LeaseStatus.ACTIVE, end_date=date.today() + timedelta(days=90)
        )
        LeaseFactory(property=rented, status=LeaseStatus.EXPIRED)  # ignored
        _geo(status=PropertyStatus.VACANT)

        resp = api_client.get("/api/v1/management/properties/map/", **_make_jwt(_mgmt()))
        by_id = {r["id"]: r for r in resp.json()["data"]}
        assert by_id[rented.id]["tenant_name"] == "Viktoriya Kim"
        assert by_id[rented.id]["lease_end_date"] == lease.end_date.isoformat()
        vacant_row = next(r for r in resp.json()["data"] if r["id"] != rented.id)
        assert vacant_row["tenant_name"] is None
        assert vacant_row["lease_end_date"] is None
