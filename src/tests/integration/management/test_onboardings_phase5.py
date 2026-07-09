from datetime import UTC, datetime, timedelta

import jwt
import pytest
from django.conf import settings
from notification.models import Notification

from core.constants import OnboardingStatus, PropertyStatus, UserRole
from tests.factories import (
    DistrictFactory,
    OwnerOnboardingFactory,
    PropertyFactory,
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
class TestManagementOnboardingsPhase5:
    def test_list_has_number(self, api_client):
        OwnerOnboardingFactory(status=OnboardingStatus.SUBMITTED)
        resp = api_client.get("/api/v1/management/onboardings/", **_make_jwt(_mgmt()))
        assert resp.status_code == 200
        rows = resp.json()["data"]
        assert rows[0]["number"].startswith("ONB-")

    def test_search_matches_property_name(self, api_client):
        district = DistrictFactory()
        p1 = PropertyFactory(name="Uchtepa Family 6-2", district=district)
        PropertyFactory(name="Other Place", district=district)
        OwnerOnboardingFactory(property=p1, status=OnboardingStatus.SUBMITTED)
        OwnerOnboardingFactory(status=OnboardingStatus.SUBMITTED)
        resp = api_client.get("/api/v1/management/onboardings/?search=Uchtepa", **_make_jwt(_mgmt()))
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["property_name"] == "Uchtepa Family 6-2"

    def test_stats_counts(self, api_client):
        OwnerOnboardingFactory(status=OnboardingStatus.SUBMITTED)
        OwnerOnboardingFactory(status=OnboardingStatus.OFFER_ACCEPTED)
        OwnerOnboardingFactory(status=OnboardingStatus.APPROVED)
        resp = api_client.get("/api/v1/management/onboardings/stats/", **_make_jwt(_mgmt()))
        data = resp.json()["data"]
        assert data["counts"]["submitted"] == 1
        assert data["counts"]["all"] == 3
        assert data["open"] == 2

    def test_detail_market_fields_from_district_comps(self, api_client):
        district = DistrictFactory()
        # Two active comps in the same district set the market band.
        PropertyFactory(district=district, tenant_charge_price=400, status=PropertyStatus.VACANT)
        PropertyFactory(district=district, tenant_charge_price=420, status=PropertyStatus.RENTED)
        subject = PropertyFactory(district=district, tenant_charge_price=999, status=PropertyStatus.PENDING_REVIEW)
        onb = OwnerOnboardingFactory(property=subject, status=OnboardingStatus.SUBMITTED)
        resp = api_client.get(f"/api/v1/management/onboardings/{onb.id}/", **_make_jwt(_mgmt()))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["market_min"] == "400.00"
        assert data["market_max"] == "420.00"
        assert data["market_median"] is not None
        assert data["suggested_price"] is not None
        assert data["number"].startswith("ONB-")

    def test_detail_degrades_without_comps(self, api_client):
        district = DistrictFactory()
        subject = PropertyFactory(district=district, status=PropertyStatus.PENDING_REVIEW)
        onb = OwnerOnboardingFactory(property=subject, status=OnboardingStatus.SUBMITTED)
        resp = api_client.get(f"/api/v1/management/onboardings/{onb.id}/", **_make_jwt(_mgmt()))
        data = resp.json()["data"]
        assert data["market_min"] is None
        assert data["market_median"] is None
        assert data["suggested_price"] is None

    def test_request_info_notifies_owner(self, api_client):
        onb = OwnerOnboardingFactory(status=OnboardingStatus.SUBMITTED)
        resp = api_client.post(
            f"/api/v1/management/onboardings/{onb.id}/request-info/",
            data={"note": "Please add bathroom photos"},
            content_type="application/json",
            **_make_jwt(_mgmt()),
        )
        assert resp.status_code == 200
        onb.refresh_from_db()
        assert "Please add bathroom photos" in onb.review_notes
        assert Notification.objects.filter(recipient=onb.owner).exists()
