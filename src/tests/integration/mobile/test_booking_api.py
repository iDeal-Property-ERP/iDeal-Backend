import base64
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import resolve
from django.utils import timezone
from marketplace.services.booking import BookingService, add_months

from api.v1.payment_providers.views import (
    ClickCompleteCallbackView,
    ClickPrepareCallbackView,
    PaymeCallbackView,
    StripeWebhookView,
)
from core.constants import PaymentProvider, PropertyStatus
from tests.factories import ExchangeRateFactory, OwnerAgreementFactory, PropertyFactory, TenantFactory
from tests.integration.property.test_api import _make_jwt

pytestmark = pytest.mark.django_db


def test_provider_callback_urls_use_class_based_views():
    assert resolve("/api/v1/payment-webhooks/payme/").func.view_class is PaymeCallbackView
    assert resolve("/api/v1/payment-webhooks/click/prepare/").func.view_class is ClickPrepareCallbackView
    assert resolve("/api/v1/payment-webhooks/click/complete/").func.view_class is ClickCompleteCallbackView
    assert resolve("/api/v1/payment-webhooks/stripe/").func.view_class is StripeWebhookView


def _listing():
    today = timezone.localdate()
    prop = PropertyFactory(status=PropertyStatus.VACANT, is_verified=True)
    listing = prop.listing
    listing.minimum_stay = 1
    listing.monthly_price = Decimal("500.00")
    listing.deposit_amount = Decimal("250.00")
    listing.currency = "USD"
    listing.owner_agreement = OwnerAgreementFactory(
        property=prop,
        owner=prop.owner,
        signed_date=today,
        start_date=today,
        end_date=add_months(today, 6) - timedelta(days=1),
        currency="USD",
    )
    listing.save()
    ExchangeRateFactory(currency="USD", rate=Decimal("12500.00"), effective_date=today)
    return listing


@override_settings(
    PAYME_ENABLED=True,
    PAYME_MERCHANT_ID="merchant",
    PAYME_KEY="secret",
    PAYME_CHECKOUT_URL="https://checkout.test",
    CLICK_ENABLED=False,
    STRIPE_ENABLED=False,
)
def test_mobile_quote_checkout_and_detail_contract(api_client):
    tenant = TenantFactory()
    listing = _listing()
    start = timezone.localdate() + timedelta(days=1)
    end = add_months(start, 1) - timedelta(days=1)
    auth = _make_jwt(tenant)

    options = api_client.get(
        f"/api/v1/mobile/home/listings/{listing.id}/booking-options/",
        **auth,
    )
    assert options.status_code == 200
    assert options.json()["data"]["eligible"] is True

    quote_response = api_client.post(
        "/api/v1/mobile/bookings/quotes/",
        data=json.dumps(
            {
                "listing_id": listing.id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            }
        ),
        content_type="application/json",
        **auth,
    )
    assert quote_response.status_code in (200, 201)
    quote = quote_response.json()["data"]
    assert quote["options"]["first_month"]["total_amount"] == "750.00"

    checkout_response = api_client.post(
        "/api/v1/mobile/bookings/checkouts/",
        data=json.dumps(
            {"quote_id": quote["id"], "provider": PaymentProvider.PAYME, "pay_full_stay": False}
        ),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mobile-booking-contract",
        **auth,
    )
    assert checkout_response.status_code in (200, 201)
    checkout = checkout_response.json()["data"]
    assert checkout["provider"] == PaymentProvider.PAYME
    assert checkout["public_token"]

    detail = api_client.get(f"/api/v1/mobile/bookings/{checkout['booking_id']}/", **auth)
    assert detail.status_code == 200
    assert detail.json()["data"]["checkout"]["public_token"] == checkout["public_token"]
    assert detail.json()["data"]["listing"]["cover_preview_url"] is None
    assert detail.json()["data"]["listing"]["cover_display_url"] is None


@override_settings(
    PAYME_ENABLED=True,
    PAYME_MERCHANT_ID="merchant",
    PAYME_KEY="secret",
    PAYME_CHECKOUT_URL="https://checkout.test",
    CLICK_ENABLED=False,
    STRIPE_ENABLED=False,
)
def test_payme_auth_and_statement_include_created_transaction(api_client):
    tenant = TenantFactory()
    listing = _listing()
    start = timezone.localdate() + timedelta(days=1)
    quote = BookingService.create_quote(
        listing=listing,
        tenant=tenant,
        start_date=start,
        end_date=add_months(start, 1) - timedelta(days=1),
    )
    checkout = BookingService.create_checkout(
        quote=quote,
        tenant=tenant,
        provider=PaymentProvider.PAYME,
        pay_full_stay=False,
        idempotency_key="payme-statement",
    )
    timestamp = int(timezone.now().timestamp() * 1000)
    unauthorized = api_client.post(
        "/api/v1/payment-webhooks/payme/",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "GetStatement", "params": {}}),
        content_type="application/json",
    )
    assert unauthorized.json()["error"]["code"] == -32504

    auth = "Basic " + base64.b64encode(b"Paycom:secret").decode()
    invalid_amount = api_client.post(
        "/api/v1/payment-webhooks/payme/",
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "CheckPerformTransaction",
                "params": {
                    "amount": "invalid",
                    "account": {"checkout": str(checkout.public_token)},
                },
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=auth,
    )
    assert invalid_amount.json()["error"]["code"] == -31001

    create = api_client.post(
        "/api/v1/payment-webhooks/payme/",
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "CreateTransaction",
                "params": {
                    "id": "payme-1",
                    "time": timestamp,
                    "amount": int(checkout.provider_amount * 100),
                    "account": {"checkout": str(checkout.public_token)},
                },
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=auth,
    )
    assert create.json()["result"]["state"] == 1

    statement = api_client.post(
        "/api/v1/payment-webhooks/payme/",
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "GetStatement",
                "params": {"from": timestamp, "to": timestamp},
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=auth,
    )
    transactions = statement.json()["result"]["transactions"]
    assert len(transactions) == 1
    assert transactions[0]["id"] == "payme-1"
    assert transactions[0]["account"]["checkout"] == str(checkout.public_token)
