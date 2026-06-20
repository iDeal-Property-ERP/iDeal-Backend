import json

import pytest
from contract.models import Lease
from marketplace.models import Booking
from notification.models import Notification

from core.constants import BookingStatus, NotificationType, PropertyStatus
from tests.factories import (
    BookingFactory,
    ListingFactory,
    OwnerAgreementFactory,
    OwnerFactory,
    PropertyFactory,
    TenantFactory,
    UserFactory,
)
from tests.integration.property.test_api import _make_jwt


@pytest.mark.django_db
class TestTenantBookings:
    def test_tenant_creates_booking(self, api_client):
        tenant = TenantFactory()
        listing = ListingFactory()

        response = api_client.post(
            "/api/v1/tenant/bookings/",
            data=json.dumps(
                {
                    "listing_id": listing.id,
                    "requested_start_date": "2026-02-01",
                    "requested_end_date": "2026-08-01",
                    "message": "Interested",
                }
            ),
            content_type="application/json",
            **_make_jwt(tenant),
        )

        assert response.status_code in (200, 201)
        booking = Booking.objects.get(tenant=tenant)
        assert booking.status == BookingStatus.REQUESTED
        assert booking.property_id == listing.property_id

    def test_tenant_lists_own_bookings(self, api_client):
        tenant = TenantFactory()
        BookingFactory(tenant=tenant)
        BookingFactory()

        response = api_client.get("/api/v1/tenant/bookings/", **_make_jwt(tenant))
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_tenant_cancels_booking(self, api_client):
        tenant = TenantFactory()
        booking = BookingFactory(tenant=tenant, status=BookingStatus.REQUESTED)

        response = api_client.post(f"/api/v1/tenant/bookings/{booking.id}/cancel/", **_make_jwt(tenant))
        assert response.status_code == 200
        booking.refresh_from_db()
        assert booking.status == BookingStatus.CANCELLED

    def test_booking_rbac(self, api_client):
        owner = OwnerFactory()
        listing = ListingFactory()
        response = api_client.post(
            "/api/v1/tenant/bookings/",
            data=json.dumps(
                {"listing_id": listing.id, "requested_start_date": "2026-02-01", "requested_end_date": "2026-08-01"}
            ),
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestManagementBookings:
    def test_approve_then_convert_creates_lease(self, api_client):
        mgmt = UserFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, status=PropertyStatus.VACANT)
        agreement = OwnerAgreementFactory(owner=owner, property=prop)
        listing = ListingFactory(property=prop, owner_agreement=agreement)
        tenant = TenantFactory()
        booking = BookingFactory(listing=listing, property=prop, tenant=tenant, status=BookingStatus.REQUESTED)

        approve = api_client.post(f"/api/v1/management/bookings/{booking.id}/approve/", **_make_jwt(mgmt))
        assert approve.status_code == 200
        booking.refresh_from_db()
        assert booking.status == BookingStatus.APPROVED

        convert = api_client.post(
            f"/api/v1/management/bookings/{booking.id}/convert/",
            data=json.dumps({"monthly_rent": "600.00"}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert convert.status_code == 200
        booking.refresh_from_db()
        assert booking.status == BookingStatus.CONVERTED
        assert booking.converted_lease_id is not None
        lease = Lease.objects.get(id=booking.converted_lease_id)
        assert lease.tenant_id == tenant.id
        prop.refresh_from_db()
        assert prop.status == PropertyStatus.RENTED
        # Lease creation deactivates the listing via the property signal.
        listing.refresh_from_db()
        assert listing.is_active is False
        assert Notification.objects.filter(recipient=tenant, type=NotificationType.BOOKING_STATUS).exists()

    def test_convert_requires_approval(self, api_client):
        mgmt = UserFactory()
        booking = BookingFactory(status=BookingStatus.REQUESTED)

        response = api_client.post(
            f"/api/v1/management/bookings/{booking.id}/convert/",
            data=json.dumps({}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert response.status_code == 400
        assert response.json()["success"] is False

    def test_reject_booking(self, api_client):
        mgmt = UserFactory()
        booking = BookingFactory(status=BookingStatus.REQUESTED)

        response = api_client.post(f"/api/v1/management/bookings/{booking.id}/reject/", **_make_jwt(mgmt))
        assert response.status_code == 200
        booking.refresh_from_db()
        assert booking.status == BookingStatus.REJECTED

    def test_management_lists_bookings(self, api_client):
        mgmt = UserFactory()
        BookingFactory()
        response = api_client.get("/api/v1/management/bookings/", data={"page": 1}, **_make_jwt(mgmt))
        assert response.status_code == 200
