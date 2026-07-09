from datetime import UTC, datetime, timedelta

import jwt
import pytest
from django.conf import settings
from vas.models import ServiceOrder

from core.constants import UserRole, VASOrderStatus, VASServiceType
from tests.factories import (
    PropertyFactory,
    ServiceCatalogItemFactory,
    ServiceOrderFactory,
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


@pytest.mark.django_db
class TestVASOrderList:
    def test_service_type_filter(self, api_client):
        ServiceOrderFactory(catalog_item=ServiceCatalogItemFactory(service_type=VASServiceType.CLEANING))
        ServiceOrderFactory(catalog_item=ServiceCatalogItemFactory(service_type=VASServiceType.INTERNET))
        resp = api_client.get("/api/v1/management/vas-orders/?service_type=internet", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["service_type"] == VASServiceType.INTERNET

    def test_search_matches_service_tenant_and_property(self, api_client):
        ServiceOrderFactory(catalog_item=ServiceCatalogItemFactory(name="Deep cleaning"))
        ServiceOrderFactory(tenant=TenantFactory(first_name="Viktoriya", last_name="Kim"))
        ServiceOrderFactory(property=PropertyFactory(name="Chilonzor Park View 7"))
        ServiceOrderFactory(catalog_item=ServiceCatalogItemFactory(name="Sofa wash"))
        headers = _make_jwt(_mgmt())

        for query, expected in (("Deep", "Deep cleaning"), ("Chilonzor", None)):
            resp = api_client.get(f"/api/v1/management/vas-orders/?search={query}", **headers)
            rows = resp.json()["data"]
            assert len(rows) == 1
            if expected:
                assert rows[0]["catalog_item_name"] == expected

        resp = api_client.get("/api/v1/management/vas-orders/?search=Viktoriya", **headers)
        assert len(resp.json()["data"]) == 1

    def test_order_by_cost(self, api_client):
        ServiceOrderFactory(cost=30)
        ServiceOrderFactory(cost=90)
        ServiceOrderFactory(cost=60)
        resp = api_client.get("/api/v1/management/vas-orders/?order=-cost", **_make_jwt(_mgmt()))
        costs = [float(r["cost"]) for r in resp.json()["data"]]
        assert costs == sorted(costs, reverse=True)

    def test_output_enriched_fields(self, api_client):
        ServiceOrderFactory(
            catalog_item=ServiceCatalogItemFactory(name="Deep cleaning", partner_name="Uy Service"),
            tenant=TenantFactory(first_name="Viktoriya", last_name="Kim"),
        )
        resp = api_client.get("/api/v1/management/vas-orders/", **_make_jwt(_mgmt()))
        row = resp.json()["data"][0]
        assert row["partner_name"] == "Uy Service"
        assert row["tenant_name"] == "Viktoriya Kim"
        assert row["property_name"]
        assert "cancellation_reason" in row
        assert "completed_at" in row


@pytest.mark.django_db
class TestVASOrderDetailAndCreate:
    def test_detail(self, api_client):
        order = ServiceOrderFactory()
        resp = api_client.get(f"/api/v1/management/vas-orders/{order.id}/", **_make_jwt(_mgmt()))
        assert resp.json()["data"]["id"] == order.id

    def test_create_defaults_cost_and_computes_commission(self, api_client):
        item = ServiceCatalogItemFactory(base_price=100, commission_rate=15, cashback_rate=5)
        tenant = TenantFactory()
        prop = PropertyFactory()
        resp = api_client.post(
            "/api/v1/management/vas-orders/",
            data={"catalog_item_id": item.id, "tenant_id": tenant.id, "property_id": prop.id},
            content_type="application/json",
            **_make_jwt(_mgmt()),
        )
        row = resp.json()["data"]
        assert float(row["cost"]) == 100.0
        assert float(row["commission_earned"]) == 15.0
        assert float(row["cashback_amount"]) == 5.0
        assert row["status"] == VASOrderStatus.REQUESTED

    def test_create_rejects_inactive_item(self, api_client):
        item = ServiceCatalogItemFactory(is_active=False)
        resp = api_client.post(
            "/api/v1/management/vas-orders/",
            data={"catalog_item_id": item.id, "tenant_id": TenantFactory().id, "property_id": PropertyFactory().id},
            content_type="application/json",
            **_make_jwt(_mgmt()),
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False


@pytest.mark.django_db
class TestVASOrderStatus:
    def test_cancel_stores_reason(self, api_client):
        order = ServiceOrderFactory()
        resp = api_client.post(
            f"/api/v1/management/vas-orders/{order.id}/status/",
            data={"status": VASOrderStatus.CANCELLED, "reason": "Tenant requested"},
            content_type="application/json",
            **_make_jwt(_mgmt()),
        )
        assert resp.json()["data"]["cancellation_reason"] == "Tenant requested"

    def test_complete_stamps_completed_at(self, api_client):
        order = ServiceOrderFactory(status=VASOrderStatus.IN_PROGRESS)
        resp = api_client.post(
            f"/api/v1/management/vas-orders/{order.id}/status/",
            data={"status": VASOrderStatus.COMPLETED},
            content_type="application/json",
            **_make_jwt(_mgmt()),
        )
        assert resp.json()["data"]["completed_at"] is not None
        order.refresh_from_db()
        assert order.completed_at is not None

    def test_terminal_statuses_reject_transitions(self, api_client):
        headers = _make_jwt(_mgmt())
        for terminal in (VASOrderStatus.COMPLETED, VASOrderStatus.CANCELLED):
            order = ServiceOrderFactory(status=terminal)
            resp = api_client.post(
                f"/api/v1/management/vas-orders/{order.id}/status/",
                data={"status": VASOrderStatus.CONFIRMED},
                content_type="application/json",
                **headers,
            )
            assert resp.status_code == 400
            assert resp.json()["success"] is False


@pytest.mark.django_db
class TestVASStatsAndPartners:
    def test_stats_counts_and_kpis(self, api_client):
        plain = ServiceCatalogItemFactory(partner_name=None)
        ServiceOrderFactory.create_batch(2, status=VASOrderStatus.REQUESTED, catalog_item=plain)
        ServiceOrderFactory(status=VASOrderStatus.CONFIRMED, catalog_item=plain)
        completed = ServiceOrderFactory(status=VASOrderStatus.COMPLETED, cost=100, catalog_item=plain)
        ServiceCatalogItemFactory(partner_name="Uy Service")
        ServiceCatalogItemFactory(partner_name="Uy Service")

        resp = api_client.get("/api/v1/management/vas-orders/stats/", **_make_jwt(_mgmt()))
        data = resp.json()["data"]
        assert data["new"] == 2
        assert data["counts"]["requested"] == 2
        assert data["counts"]["confirmed"] == 1
        assert data["counts"]["completed"] == 1
        assert data["counts"]["all"] == 4
        # completed_at is NULL on the factory row → falls back to updated_at (now)
        assert float(data["revenue_30d"]) == float(completed.cost)
        assert float(data["commission_30d"]) == float(completed.commission_earned)
        assert data["catalog_count"] == 3
        assert data["partners_count"] == 1

    def test_partners_grouping(self, api_client):
        cleaning = ServiceCatalogItemFactory(partner_name="Uy Service", service_type=VASServiceType.CLEANING)
        ServiceCatalogItemFactory(partner_name="Uy Service", service_type=VASServiceType.HANDYMAN)
        ServiceCatalogItemFactory(partner_name="UzOnline", service_type=VASServiceType.INTERNET)
        ServiceOrderFactory(catalog_item=cleaning, status=VASOrderStatus.COMPLETED, cost=200)

        resp = api_client.get("/api/v1/management/vas-partners/", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert [r["partner_name"] for r in rows] == ["Uy Service", "UzOnline"]
        uy = rows[0]
        assert uy["services_count"] == 2
        assert set(uy["service_types"]) == {VASServiceType.CLEANING, VASServiceType.HANDYMAN}
        assert uy["orders_total"] == 1
        assert float(uy["commission_30d"]) == float(ServiceOrder.objects.get(catalog_item=cleaning).commission_earned)


@pytest.mark.django_db
class TestCatalogSearch:
    def test_search_filters_catalog(self, api_client):
        ServiceCatalogItemFactory(name="Deep cleaning")
        ServiceCatalogItemFactory(name="Router setup", partner_name="UzOnline")
        resp = api_client.get("/api/v1/vas/catalog/?search=uzonline", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["name"] == "Router setup"
