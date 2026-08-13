from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone
from finance.models import Payment
from marketplace.models import ProviderEvent
from marketplace.services.booking import BookingService, BookingValidationError, add_months

from core.constants import (
    BookingStatus,
    LeaseStatus,
    PaymentCheckoutStatus,
    PaymentKind,
    PaymentProvider,
    PaymentStatus,
    PropertyStatus,
)
from tests.factories import ExchangeRateFactory, OwnerAgreementFactory, PropertyFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _bookable_listing(months=3):
    today = timezone.localdate()
    prop = PropertyFactory(status=PropertyStatus.VACANT, is_verified=True)
    listing = prop.listing
    listing.minimum_stay = 1
    listing.monthly_price = Decimal("500.00")
    listing.deposit_amount = Decimal("250.00")
    listing.currency = "USD"
    agreement = OwnerAgreementFactory(
        property=prop,
        owner=prop.owner,
        signed_date=today,
        start_date=today,
        end_date=add_months(today, months) - timedelta(days=1),
        currency="USD",
    )
    listing.owner_agreement = agreement
    listing.save()
    return listing, agreement


@override_settings(PAYME_ENABLED=True, CLICK_ENABLED=False, STRIPE_ENABLED=False)
def test_quote_prices_monthly_anniversaries_and_partial_final_period():
    listing, _ = _bookable_listing()
    start = timezone.localdate() + timedelta(days=1)
    end = add_months(start, 1) + timedelta(days=14)

    quote = BookingService.create_quote(listing=listing, tenant=TenantFactory(), start_date=start, end_date=end)

    assert quote.first_period_rent == Decimal("500.00")
    assert quote.full_stay_rent > Decimal("500.00")
    assert quote.first_month_total == Decimal("750.00")
    assert len(quote.periods) == 2
    assert quote.periods[-1]["end_date"] == end.isoformat()


@override_settings(PAYME_ENABLED=True, CLICK_ENABLED=False, STRIPE_ENABLED=False)
def test_managed_listing_eligibility_is_date_derived_when_legacy_active_flag_is_false():
    listing, _ = _bookable_listing()
    listing.is_active = False
    listing.save(update_fields=["is_active", "updated_at"])

    result = BookingService.eligibility(listing)

    assert result["eligible"] is True


@override_settings(PAYME_ENABLED=True, CLICK_ENABLED=False, STRIPE_ENABLED=False)
def test_quote_rejects_gap_between_explicit_agreement_renewals():
    listing, agreement = _bookable_listing(months=1)
    start = timezone.localdate() + timedelta(days=1)
    OwnerAgreementFactory(
        previous_agreement=agreement,
        property=listing.property,
        owner=listing.property.owner,
        start_date=agreement.end_date + timedelta(days=2),
        end_date=agreement.end_date + timedelta(days=60),
        currency="USD",
    )

    with pytest.raises(BookingValidationError, match="owner_agreement_gap"):
        BookingService.create_quote(
            listing=listing,
            tenant=TenantFactory(),
            start_date=start,
            end_date=agreement.end_date + timedelta(days=3),
        )


@override_settings(
    PAYME_ENABLED=True,
    PAYME_MERCHANT_ID="merchant",
    PAYME_CHECKOUT_URL="https://checkout.test",
    CLICK_ENABLED=False,
    STRIPE_ENABLED=False,
)
def test_successful_checkout_fulfills_booking_and_creates_first_month_payments():
    listing, _ = _bookable_listing()
    tenant = TenantFactory()
    start = timezone.localdate() + timedelta(days=1)
    end = add_months(start, 2) - timedelta(days=1)
    ExchangeRateFactory(currency="USD", rate=Decimal("12500.00"), effective_date=timezone.localdate())
    quote = BookingService.create_quote(listing=listing, tenant=tenant, start_date=start, end_date=end)

    checkout = BookingService.create_checkout(
        quote=quote,
        tenant=tenant,
        provider=PaymentProvider.PAYME,
        pay_full_stay=False,
        idempotency_key="booking-test-key",
    )
    checkout = BookingService.fulfill_checkout(
        checkout_id=checkout.id,
        external_event_id="payme-perform-1",
        event_type="PerformTransaction",
        payload={"id": "payme-perform-1"},
        succeeded=True,
    )

    checkout.booking.refresh_from_db()
    assert checkout.status == PaymentCheckoutStatus.SUCCEEDED
    assert checkout.booking.status == BookingStatus.CONFIRMED
    assert checkout.booking.converted_lease.status == LeaseStatus.PENDING_SIGNATURE
    assert checkout.booking.converted_lease.agreement_segments.count() == 1
    assert Payment.objects.filter(checkout=checkout, kind=PaymentKind.DEPOSIT, status=PaymentStatus.PAID).count() == 1
    rent = list(Payment.objects.filter(checkout=checkout, kind=PaymentKind.RENT).order_by("due_date"))
    assert [payment.status for payment in rent] == [PaymentStatus.PAID, PaymentStatus.PENDING]
    assert rent[0].coverage_allocations.exists()

    repeated = BookingService.fulfill_checkout(
        checkout_id=checkout.id,
        external_event_id="payme-perform-1",
        event_type="PerformTransaction",
        payload={"id": "payme-perform-1"},
        succeeded=True,
    )
    assert repeated.status == PaymentCheckoutStatus.SUCCEEDED
    assert ProviderEvent.objects.filter(external_event_id="payme-perform-1").count() == 1
