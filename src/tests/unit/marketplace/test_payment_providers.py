from decimal import Decimal
from types import SimpleNamespace

from django.test import override_settings
from marketplace.services.payments import payment_provider_registry
from marketplace.services.payments.providers import ClickProvider, PaymentProvider, PaymeProvider, StripeProvider

from core.constants import PaymentProvider as PaymentProviderCode


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def test_all_provider_adapters_inherit_the_common_base():
    assert issubclass(PaymeProvider, PaymentProvider)
    assert issubclass(ClickProvider, PaymentProvider)
    assert issubclass(StripeProvider, PaymentProvider)


@override_settings(PAYME_ENABLED=True, CLICK_ENABLED=False, STRIPE_ENABLED=True)
def test_registry_exposes_only_enabled_provider_codes():
    assert payment_provider_registry.enabled_codes() == [PaymentProviderCode.PAYME, PaymentProviderCode.STRIPE]
    assert isinstance(payment_provider_registry.get(PaymentProviderCode.CLICK), ClickProvider)


def test_local_providers_share_locked_uzs_conversion_contract():
    for provider in (PaymeProvider(), ClickProvider()):
        prepared = provider.prepare_amount(
            original_amount=Decimal("10.00"),
            original_currency="USD",
            fx_rate=Decimal("12500"),
            quantize=_money,
        )

        assert prepared.amount == Decimal("125000.00")
        assert prepared.currency == "UZS"
        assert prepared.fx_rate == Decimal("12500")


def test_stripe_preserves_listing_amount_and_currency():
    prepared = StripeProvider().prepare_amount(
        original_amount=Decimal("10.00"),
        original_currency="USD",
        fx_rate=Decimal("12500"),
        quantize=_money,
    )

    assert prepared.amount == Decimal("10.00")
    assert prepared.currency == "USD"
    assert prepared.fx_rate is None


@override_settings(PAYME_MERCHANT_ID="merchant", PAYME_CHECKOUT_URL="https://payme.test")
def test_payme_provider_builds_hosted_checkout_url():
    checkout = SimpleNamespace(provider_amount=Decimal("12.34"), public_token="opaque")

    hosted = PaymeProvider().create_hosted_checkout(checkout)

    assert hosted.url.startswith("https://payme.test/")
    assert hosted.external_id is None


@override_settings(
    CLICK_SERVICE_ID="service",
    CLICK_MERCHANT_ID="merchant",
    CLICK_CHECKOUT_URL="https://click.test/pay",
)
def test_click_provider_builds_hosted_checkout_url():
    checkout = SimpleNamespace(provider_amount=Decimal("12.34"), public_token="opaque")

    hosted = ClickProvider().create_hosted_checkout(checkout)

    assert hosted.url.startswith("https://click.test/pay?")
    assert "transaction_param=opaque" in hosted.url
    assert hosted.external_id is None
