import datetime
from http import HTTPStatus

import pytest

from core.constants import LeaseStatus, ListingStatus, OwnerAgreementStatus, PropertyStatus
from tests.factories import LeaseFactory, ListingFactory, OwnerAgreementFactory, PropertyFactory

pytestmark = pytest.mark.django_db


class TestMarketplaceAvailabilityFilter:
    def test_vacant_without_dates(self, client):
        # A property that is vacant
        p_vacant = PropertyFactory(status=PropertyStatus.VACANT)
        ListingFactory(property=p_vacant, status=ListingStatus.PUBLISHED, is_active=True)

        # A property that is rented
        p_rented = PropertyFactory(status=PropertyStatus.RENTED)
        oa = OwnerAgreementFactory(property=p_rented, status=OwnerAgreementStatus.ACTIVE)
        ListingFactory(property=p_rented, status=ListingStatus.PUBLISHED, is_active=True)
        LeaseFactory(property=p_rented, owner_agreement=oa, status=LeaseStatus.ACTIVE)

        resp = client.get("/api/v1/marketplace/listings/")
        assert resp.status_code == HTTPStatus.OK
        data = resp.json()
        assert data["success"] is True

        # Only the vacant property should be returned
        ids = [x["property"]["id"] for x in data["data"]["page"]["object_list"]]
        assert p_vacant.id in ids
        assert p_rented.id not in ids

    def test_availability_with_dates(self, client):
        today = datetime.date.today()
        start = today + datetime.timedelta(days=10)
        end = today + datetime.timedelta(days=20)

        # 1. Rented property with an owner agreement covering a feasible date range, and
        # no active lease in the unavoidable core of the requested stay.
        p_available = PropertyFactory(status=PropertyStatus.RENTED)
        ListingFactory(property=p_available, status=ListingStatus.PUBLISHED, is_active=True)
        # Default flexibility is ±3 days, so the agreement may start as late as
        # start+3 and end as early as end-3 while still matching the preference.
        oa_start = start + datetime.timedelta(days=3)
        oa_end = end - datetime.timedelta(days=3)
        oa_available = OwnerAgreementFactory(
            property=p_available, status=OwnerAgreementStatus.ACTIVE, start_date=oa_start, end_date=oa_end
        )
        # This lease overlaps the preferred start date, but it ends before the latest
        # acceptable move-in date, so the flexible window still has a feasible interval.
        LeaseFactory(
            property=p_available,
            owner_agreement=oa_available,
            status=LeaseStatus.ACTIVE,
            start_date=today - datetime.timedelta(days=30),
            end_date=start + datetime.timedelta(days=2),
        )

        # 2. Property that has an active lease overlapping the unavoidable core period.
        p_overlap = PropertyFactory(status=PropertyStatus.RENTED)
        ListingFactory(property=p_overlap, status=ListingStatus.PUBLISHED, is_active=True)
        oa_overlap = OwnerAgreementFactory(
            property=p_overlap,
            status=OwnerAgreementStatus.ACTIVE,
            start_date=today,
            end_date=today + datetime.timedelta(days=30),
        )
        # Overlapping lease (ends during the period)
        LeaseFactory(
            property=p_overlap,
            owner_agreement=oa_overlap,
            status=LeaseStatus.ACTIVE,
            start_date=today,
            end_date=today + datetime.timedelta(days=15),
        )

        # 3. Property that has NO active owner agreement covering the period.
        p_no_oa = PropertyFactory(status=PropertyStatus.VACANT)
        ListingFactory(property=p_no_oa, status=ListingStatus.PUBLISHED, is_active=True)
        # Agreement ends before the earliest acceptable move-out.
        OwnerAgreementFactory(
            property=p_no_oa,
            status=OwnerAgreementStatus.ACTIVE,
            start_date=today - datetime.timedelta(days=30),
            end_date=end - datetime.timedelta(days=4),
        )

        resp = client.get(f"/api/v1/marketplace/listings/?start_date={start.isoformat()}&end_date={end.isoformat()}")
        assert resp.status_code == HTTPStatus.OK
        data = resp.json()
        assert data["success"] is True

        ids = [x["property"]["id"] for x in data["data"]["page"]["object_list"]]
        assert p_available.id in ids
        assert p_overlap.id not in ids
        assert p_no_oa.id not in ids

    def test_date_validation_errors(self, client):
        today = datetime.date.today()
        # Partial dates
        resp = client.get(f"/api/v1/marketplace/listings/?start_date={today.isoformat()}")
        assert resp.status_code == HTTPStatus.BAD_REQUEST
        assert resp.json()["success"] is False

        # End before start
        end = today - datetime.timedelta(days=1)
        resp = client.get(f"/api/v1/marketplace/listings/?start_date={today.isoformat()}&end_date={end.isoformat()}")
        assert resp.status_code == HTTPStatus.BAD_REQUEST
        assert resp.json()["success"] is False

        # Negative flex
        end = today + datetime.timedelta(days=1)
        resp = client.get(
            f"/api/v1/marketplace/listings/?start_date={today.isoformat()}&end_date={end.isoformat()}&flexibility_days=-1"
        )
        assert resp.status_code == HTTPStatus.BAD_REQUEST
        assert resp.json()["success"] is False
