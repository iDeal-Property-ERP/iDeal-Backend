from datetime import UTC, date, datetime, timedelta

import jwt
import pytest
from django.conf import settings
from django.utils import timezone

from core.constants import (
    CostBearer,
    PaymentStatus,
    PayoutStatus,
    ServiceRequestStatus,
    UserRole,
    VASOrderStatus,
)
from tests.factories import (
    ExchangeRateFactory,
    PaymentFactory,
    PayoutScheduleFactory,
    ServiceCatalogItemFactory,
    ServiceOrderFactory,
    ServiceRequestFactory,
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


def _seed_base():
    """One paid $500 payment + one paid $380 payout in the current month, USD@12500."""
    ExchangeRateFactory(currency="USD", rate=12500)
    today = date.today()
    PaymentFactory(status=PaymentStatus.PAID, amount=500, payment_date=today)
    PayoutScheduleFactory(status=PayoutStatus.PAID, amount=380, paid_date=today)


@pytest.mark.django_db
class TestPnlDefaults:
    def test_paramless_call_reproduces_legacy_numbers_and_shape(self, api_client):
        _seed_base()
        # present but excluded by the default sources
        ServiceOrderFactory(status=VASOrderStatus.COMPLETED, cost=100)
        ServiceRequestFactory(
            status=ServiceRequestStatus.RESOLVED, resolved_at=timezone.now(), cost=50, cost_bearer=None
        )

        resp = api_client.get("/api/v1/management/pnl/", **_make_jwt(_mgmt()))
        data = resp.json()["data"]
        assert data["summary"]["gross_revenue"] == "500.00"
        assert data["summary"]["owner_payouts"] == "380.00"
        assert data["summary"]["net_profit"] == "120.00"
        # tax stays UZS: 120 USD * 12500 * 4%
        assert data["summary"]["tax"] == "60000.00"
        assert len(data["monthly"]) == date.today().month
        assert {"summary", "monthly", "growth", "investor"} <= set(data)
        # additive phase-6 keys
        assert data["year"] == date.today().year
        assert data["currency"] == "USD"
        assert data["sources"] == ["lease", "payouts"]
        assert data["breakdown"] is not None


@pytest.mark.django_db
class TestPnlSources:
    def test_vas_source_adds_commission_to_revenue(self, api_client):
        _seed_base()
        item = ServiceCatalogItemFactory(commission_rate=15)
        ServiceOrderFactory(status=VASOrderStatus.COMPLETED, cost=100, catalog_item=item)

        resp = api_client.get("/api/v1/management/pnl/?sources=lease,vas,payouts", **_make_jwt(_mgmt()))
        data = resp.json()["data"]
        assert data["summary"]["gross_revenue"] == "515.00"
        assert data["summary"]["net_profit"] == "135.00"
        revenue_sources = {r["source"] for r in data["breakdown"]["revenue"]}
        assert revenue_sources == {"lease", "vas"}
        assert data["breakdown"]["vas_by_service_type"]

    def test_maintenance_source_adds_platform_costs_to_expenses(self, api_client):
        _seed_base()
        ServiceRequestFactory(
            status=ServiceRequestStatus.RESOLVED, resolved_at=timezone.now(), cost=50, cost_bearer=None
        )
        # owner-borne cost never counts
        ServiceRequestFactory(
            status=ServiceRequestStatus.RESOLVED, resolved_at=timezone.now(), cost=70, cost_bearer=CostBearer.OWNER
        )

        resp = api_client.get("/api/v1/management/pnl/?sources=lease,payouts,maintenance", **_make_jwt(_mgmt()))
        data = resp.json()["data"]
        assert data["summary"]["owner_payouts"] == "430.00"
        assert data["summary"]["net_profit"] == "70.00"

    def test_excluding_payouts_zeroes_expenses(self, api_client):
        _seed_base()
        resp = api_client.get("/api/v1/management/pnl/?sources=lease", **_make_jwt(_mgmt()))
        data = resp.json()["data"]
        assert data["summary"]["owner_payouts"] == "0.00"
        assert data["summary"]["net_profit"] == "500.00"

    def test_invalid_sources_fall_back_to_default(self, api_client):
        _seed_base()
        resp = api_client.get("/api/v1/management/pnl/?sources=bogus", **_make_jwt(_mgmt()))
        assert resp.json()["data"]["sources"] == ["lease", "payouts"]


@pytest.mark.django_db
class TestPnlYearAndCurrency:
    def test_year_param_scopes_report(self, api_client):
        ExchangeRateFactory(currency="USD", rate=12500)
        last_year = date.today().year - 1
        PaymentFactory(status=PaymentStatus.PAID, amount=200, payment_date=date(last_year, 6, 15))

        headers = _make_jwt(_mgmt())
        past = api_client.get(f"/api/v1/management/pnl/?year={last_year}", **headers).json()["data"]
        assert past["year"] == last_year
        assert len(past["monthly"]) == 12
        assert past["monthly"][5]["revenue"] == "200.00"
        assert past["growth"]["projected"] == []

        current = api_client.get("/api/v1/management/pnl/", **headers).json()["data"]
        assert all(row["revenue"] == "0.00" for row in current["monthly"])

    def test_currency_uzs(self, api_client):
        _seed_base()
        resp = api_client.get("/api/v1/management/pnl/?currency=UZS", **_make_jwt(_mgmt()))
        data = resp.json()["data"]
        assert data["currency"] == "UZS"
        assert data["summary"]["gross_revenue"] == "6250000.00"
        assert data["summary"]["tax"] == "60000.00"


@pytest.mark.django_db
class TestPnlBreakdown:
    def test_shares_sum_to_100(self, api_client):
        _seed_base()
        item = ServiceCatalogItemFactory(commission_rate=15)
        ServiceOrderFactory(status=VASOrderStatus.COMPLETED, cost=100, catalog_item=item)
        ServiceRequestFactory(
            status=ServiceRequestStatus.RESOLVED, resolved_at=timezone.now(), cost=50, cost_bearer=None
        )
        resp = api_client.get("/api/v1/management/pnl/?sources=lease,vas,payouts,maintenance", **_make_jwt(_mgmt()))
        breakdown = resp.json()["data"]["breakdown"]
        for group in ("revenue", "expenses"):
            total = sum(float(r["share"]) for r in breakdown[group])
            assert abs(total - 100.0) < 0.5

    def test_degrades_without_exchange_rate(self, api_client):
        # no ExchangeRate rows at all: USD buckets can't convert to UZS and contribute 0
        PaymentFactory(status=PaymentStatus.PAID, amount=500, payment_date=date.today())
        resp = api_client.get("/api/v1/management/pnl/", **_make_jwt(_mgmt()))
        assert resp.status_code == 200
        assert resp.json()["data"]["summary"]["gross_revenue"] == "0.00"
