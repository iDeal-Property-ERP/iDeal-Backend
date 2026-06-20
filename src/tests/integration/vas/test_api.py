import json
from decimal import Decimal

import pytest
from notification.models import Notification
from vas.models import ServiceOrder

from core.constants import LeaseStatus, NotificationType, VASOrderStatus
from tests.factories import (
    LeaseFactory,
    OwnerFactory,
    PropertyFactory,
    ServiceCatalogItemFactory,
    ServiceOrderFactory,
    TenantFactory,
    UserFactory,
)
from tests.integration.property.test_api import _make_jwt


@pytest.mark.django_db
class TestVASCatalog:
    def test_anyone_authenticated_can_list(self, api_client):
        tenant = TenantFactory()
        ServiceCatalogItemFactory(is_active=True)

        response = api_client.get("/api/v1/vas/catalog/", **_make_jwt(tenant))
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_management_can_create(self, api_client):
        mgmt = UserFactory()
        response = api_client.post(
            "/api/v1/vas/catalog/",
            data=json.dumps(
                {"name": "Deep Clean", "service_type": "cleaning", "base_price": "120.00", "commission_rate": "15.00"}
            ),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert response.status_code in (200, 201)

    def test_tenant_cannot_create(self, api_client):
        tenant = TenantFactory()
        response = api_client.post(
            "/api/v1/vas/catalog/",
            data=json.dumps({"name": "X", "base_price": "10.00"}),
            content_type="application/json",
            **_make_jwt(tenant),
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestTenantVASOrders:
    def test_tenant_orders_service(self, api_client):
        tenant = TenantFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner)
        LeaseFactory(tenant=tenant, property=prop, status=LeaseStatus.ACTIVE)
        item = ServiceCatalogItemFactory(base_price=Decimal("100.00"), commission_rate=Decimal("15.00"))

        response = api_client.post(
            "/api/v1/tenant/vas-orders/",
            data=json.dumps({"catalog_item_id": item.id}),
            content_type="application/json",
            **_make_jwt(tenant),
        )
        assert response.status_code in (200, 201)
        order = ServiceOrder.objects.get(tenant=tenant)
        assert order.cost == Decimal("100.00")
        assert order.commission_earned == Decimal("15.00")

    def test_order_requires_active_lease(self, api_client):
        tenant = TenantFactory()
        item = ServiceCatalogItemFactory()
        response = api_client.post(
            "/api/v1/tenant/vas-orders/",
            data=json.dumps({"catalog_item_id": item.id}),
            content_type="application/json",
            **_make_jwt(tenant),
        )
        assert response.status_code == 400

    def test_tenant_lists_own_orders(self, api_client):
        tenant = TenantFactory()
        ServiceOrderFactory(tenant=tenant)
        ServiceOrderFactory()
        response = api_client.get("/api/v1/tenant/vas-orders/", **_make_jwt(tenant))
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1


@pytest.mark.django_db
class TestManagementVASOrders:
    def test_status_update_notifies_tenant(self, api_client):
        mgmt = UserFactory()
        tenant = TenantFactory()
        order = ServiceOrderFactory(tenant=tenant, status=VASOrderStatus.REQUESTED)

        response = api_client.post(
            f"/api/v1/management/vas-orders/{order.id}/status/",
            data=json.dumps({"status": "confirmed"}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert response.status_code == 200
        order.refresh_from_db()
        assert order.status == VASOrderStatus.CONFIRMED
        assert Notification.objects.filter(recipient=tenant, type=NotificationType.SERVICE_ORDER_STATUS).exists()

    def test_invalid_status_rejected(self, api_client):
        mgmt = UserFactory()
        order = ServiceOrderFactory()
        response = api_client.post(
            f"/api/v1/management/vas-orders/{order.id}/status/",
            data=json.dumps({"status": "bogus"}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert response.status_code == 400

    def test_management_lists_orders(self, api_client):
        mgmt = UserFactory()
        ServiceOrderFactory()
        response = api_client.get("/api/v1/management/vas-orders/", data={"page": 1}, **_make_jwt(mgmt))
        assert response.status_code == 200
