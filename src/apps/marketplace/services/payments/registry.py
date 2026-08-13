from marketplace.services.payments.providers import ClickProvider, PaymentProvider, PaymeProvider, StripeProvider


class PaymentProviderRegistry:
    def __init__(self, providers: tuple[PaymentProvider, ...]):
        self._providers = {provider.code: provider for provider in providers}

    def get(self, code: str) -> PaymentProvider:
        try:
            return self._providers[code]
        except KeyError as exc:
            raise LookupError(f"Unknown payment provider: {code}") from exc

    def enabled_codes(self) -> list[str]:
        return [provider.code for provider in self._providers.values() if provider.is_enabled]

    def all(self) -> tuple[PaymentProvider, ...]:
        return tuple(self._providers.values())


payment_provider_registry = PaymentProviderRegistry((PaymeProvider(), ClickProvider(), StripeProvider()))
