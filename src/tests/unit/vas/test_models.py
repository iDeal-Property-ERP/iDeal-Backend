from decimal import Decimal

import pytest

from tests.factories import ServiceCatalogItemFactory, ServiceOrderFactory


@pytest.mark.django_db
class TestServiceOrderCommission:
    def test_commission_and_cashback_computed_on_save(self):
        item = ServiceCatalogItemFactory(commission_rate=Decimal("15.00"), cashback_rate=Decimal("5.00"))
        order = ServiceOrderFactory(catalog_item=item, cost=Decimal("200.00"))
        assert order.commission_earned == Decimal("30.00")
        assert order.cashback_amount == Decimal("10.00")

    def test_zero_rates(self):
        item = ServiceCatalogItemFactory(commission_rate=Decimal("0.00"), cashback_rate=Decimal("0.00"))
        order = ServiceOrderFactory(catalog_item=item, cost=Decimal("200.00"))
        assert order.commission_earned == Decimal("0.00")
        assert order.cashback_amount == Decimal("0.00")
