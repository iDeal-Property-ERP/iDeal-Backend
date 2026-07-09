import json
from datetime import date, timedelta

import pytest
from finance.models import Payment

from core.constants import BookingStatus, LeaseStatus, PaymentStatus
from tests.factories import BookingFactory, LeaseFactory, OwnerAgreementFactory
from tests.integration.property.test_api import _make_jwt


def _approved_booking_with_agreement():
    booking = BookingFactory(status=BookingStatus.APPROVED)
    OwnerAgreementFactory(property=booking.property)
    return booking


@pytest.mark.django_db
class TestBookingConvert:
    def test_convert_with_term_overrides(self, api_client, management):
        booking = _approved_booking_with_agreement()
        start = date.today() + timedelta(days=7)
        end = start + timedelta(days=365)
        response = api_client.post(
            f"/api/v1/management/bookings/{booking.id}/convert/",
            data=json.dumps(
                {
                    "monthly_rent": "600.00",
                    "deposit": "600.00",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                }
            ),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        booking.refresh_from_db()
        assert booking.status == BookingStatus.CONVERTED
        lease = booking.converted_lease
        assert lease.start_date == start
        assert lease.end_date == end
        assert str(lease.monthly_rent) == "600.00"

    def test_convert_creates_pending_deposit_payment(self, api_client, management):
        booking = _approved_booking_with_agreement()
        api_client.post(
            f"/api/v1/management/bookings/{booking.id}/convert/",
            data=json.dumps({"deposit": "550.00"}),
            content_type="application/json",
            **_make_jwt(management),
        )
        booking.refresh_from_db()
        payment = Payment.objects.get(lease=booking.converted_lease)
        assert payment.status == PaymentStatus.PENDING
        assert str(payment.amount) == "550.00"

    def test_convert_conflict_returns_409(self, api_client, management):
        booking = _approved_booking_with_agreement()
        # Property already has an active lease → conflict.
        LeaseFactory(property=booking.property, status=LeaseStatus.ACTIVE)
        response = api_client.post(
            f"/api/v1/management/bookings/{booking.id}/convert/",
            data=json.dumps({}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 409
        assert response.json()["error"] == "lease_conflict"
        booking.refresh_from_db()
        assert booking.status == BookingStatus.APPROVED

    def test_convert_without_agreement_fails(self, api_client, management):
        booking = BookingFactory(status=BookingStatus.APPROVED)
        response = api_client.post(
            f"/api/v1/management/bookings/{booking.id}/convert/",
            data=json.dumps({}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 400

    def test_convert_rejects_bad_date_range(self, api_client, management):
        booking = _approved_booking_with_agreement()
        start = date.today() + timedelta(days=30)
        response = api_client.post(
            f"/api/v1/management/bookings/{booking.id}/convert/",
            data=json.dumps({"start_date": start.isoformat(), "end_date": start.isoformat()}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert response.status_code == 400
