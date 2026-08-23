from datetime import UTC, datetime, timedelta

import jwt
import pytest
from django.conf import settings
from marketplace.models import ListingViewActivity

from core.constants import ListingStatus, PropertyStatus
from tests.factories import DistrictFactory, ListingFactory, OwnerFactory, PropertyFactory, TenantFactory

pytestmark = pytest.mark.django_db

MY_LISTINGS_URL = "/api/v1/mobile/my-listings/"
MY_LISTINGS_STATS_URL = "/api/v1/mobile/my-listings/stats/"


def _make_jwt(user):
    payload = {
        "sub": str(user.id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class TestMobileMyListingsAuth:
    def test_stats_requires_authentication(self, api_client):
        response = api_client.get(MY_LISTINGS_STATS_URL)
        assert response.status_code == 401
        assert response.json()["success"] is False

    def test_list_requires_authentication(self, api_client):
        response = api_client.get(MY_LISTINGS_URL)
        assert response.status_code == 401
        assert response.json()["success"] is False


class TestMobileMyListingsStats:
    def test_empty_stats_for_new_user(self, api_client):
        user = TenantFactory()
        response = api_client.get(MY_LISTINGS_STATS_URL, **_make_jwt(user))
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"] == {
            "total_count": 0,
            "approved_count": 0,
            "pending_count": 0,
            "rented_count": 0,
            "rejected_count": 0,
            "draft_count": 0,
            "archived_count": 0,
        }

    def test_stats_aggregation_across_statuses(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory(name="Yunusobod")

        # 1. Approved (Vacant property with published listing)
        p_approved = PropertyFactory(owner=owner, district=district, status=PropertyStatus.VACANT, ask_price=800)
        ListingFactory(property=p_approved, status=ListingStatus.PUBLISHED, is_active=True, monthly_price=800)

        # 2. Pending review (Property in pending review)
        p_pending = PropertyFactory(owner=owner, district=district, status=PropertyStatus.PENDING_REVIEW, ask_price=600)
        ListingFactory(property=p_pending, status=ListingStatus.PENDING_REVIEW, is_active=False)

        # 3. Rented property
        p_rented = PropertyFactory(owner=owner, district=district, status=PropertyStatus.RENTED, ask_price=1200)
        ListingFactory(property=p_rented, status=ListingStatus.PUBLISHED, is_active=False)

        # 4. Rejected listing
        p_rejected = PropertyFactory(owner=owner, district=district, status=PropertyStatus.DRAFT, ask_price=450)
        ListingFactory(
            property=p_rejected,
            status=ListingStatus.REJECTED,
            is_active=False,
            rejection_reason="Photos unclear",
        )

        response = api_client.get(MY_LISTINGS_STATS_URL, **_make_jwt(owner))
        assert response.status_code == 200
        data = response.json()["data"]

        assert data["total_count"] == 4
        assert data["approved_count"] == 1
        assert data["pending_count"] == 1
        assert data["rented_count"] == 1
        assert data["rejected_count"] == 1


class TestMobileMyListingsList:
    def test_isolation_between_users(self, api_client):
        owner1 = OwnerFactory()
        owner2 = OwnerFactory()

        p1 = PropertyFactory(owner=owner1, name="Owner 1 Flat", status=PropertyStatus.VACANT)
        ListingFactory(property=p1, status=ListingStatus.PUBLISHED)

        p2 = PropertyFactory(owner=owner2, name="Owner 2 Flat", status=PropertyStatus.VACANT)
        ListingFactory(property=p2, status=ListingStatus.PUBLISHED)

        response = api_client.get(MY_LISTINGS_URL, **_make_jwt(owner1))
        assert response.status_code == 200
        listings = response.json()["data"]["listings"]
        assert len(listings) == 1
        assert listings[0]["title"] == "Owner 1 Flat"

    def test_filter_by_status(self, api_client):
        owner = OwnerFactory()

        p_approved = PropertyFactory(owner=owner, name="Approved Property", status=PropertyStatus.VACANT)
        ListingFactory(property=p_approved, status=ListingStatus.PUBLISHED)

        p_pending = PropertyFactory(owner=owner, name="Pending Property", status=PropertyStatus.PENDING_REVIEW)
        ListingFactory(property=p_pending, status=ListingStatus.PENDING_REVIEW)

        p_rented = PropertyFactory(owner=owner, name="Rented Property", status=PropertyStatus.RENTED)
        ListingFactory(property=p_rented, status=ListingStatus.PUBLISHED)

        # Filter: approved
        res_approved = api_client.get(f"{MY_LISTINGS_URL}?status=approved", **_make_jwt(owner))
        items_approved = res_approved.json()["data"]["listings"]
        assert len(items_approved) == 1
        assert items_approved[0]["title"] == "Approved Property"
        assert items_approved[0]["status"] == "approved"
        # Stats are always included
        assert res_approved.json()["data"]["stats"]["total_count"] == 3
        assert res_approved.json()["data"]["stats"]["approved_count"] == 1

        # Filter: pending
        res_pending = api_client.get(f"{MY_LISTINGS_URL}?status=pending", **_make_jwt(owner))
        items_pending = res_pending.json()["data"]["listings"]
        assert len(items_pending) == 1
        assert items_pending[0]["title"] == "Pending Property"
        assert items_pending[0]["status"] == "pending"

        # Filter: rented
        res_rented = api_client.get(f"{MY_LISTINGS_URL}?status=rented", **_make_jwt(owner))
        items_rented = res_rented.json()["data"]["listings"]
        assert len(items_rented) == 1
        assert items_rented[0]["title"] == "Rented Property"
        assert items_rented[0]["status"] == "rented"

        # Filter: all
        res_all = api_client.get(f"{MY_LISTINGS_URL}?status=all", **_make_jwt(owner))
        items_all = res_all.json()["data"]["listings"]
        assert len(items_all) == 3

    def test_listing_view_count_and_details(self, api_client):
        owner = OwnerFactory()
        viewer = TenantFactory()
        p = PropertyFactory(
            owner=owner, name="Viewed Property", status=PropertyStatus.VACANT, rooms=2, area_sqm=65, ask_price=700
        )
        listing = p.listing
        listing.monthly_price = 700
        listing.currency = "USD"
        listing.save()

        ListingViewActivity.objects.create(user=viewer, listing=listing)

        response = api_client.get(MY_LISTINGS_URL, **_make_jwt(owner))
        assert response.status_code == 200
        item = response.json()["data"]["listings"][0]
        assert item["title"] == "Viewed Property"
        assert item["price"] == 700.0
        assert item["currency"] == "USD"
        assert item["rooms"] == 2
        assert item["area_sqm"] == 65
        assert item["views_count"] == 1
