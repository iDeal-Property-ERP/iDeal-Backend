from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from marketplace.models import PaymentCheckout


class PaymentProviderError(ValueError):
    """A provider cannot prepare or launch the requested checkout."""


@dataclass(frozen=True)
class ProviderAmount:
    amount: Decimal
    currency: str
    fx_rate: Decimal | None


@dataclass(frozen=True)
class HostedCheckout:
    url: str
    external_id: str | None = None


class PaymentProvider(ABC):
    """Provider adapter contract shared by hosted checkout and callbacks."""

    code: ClassVar[str]
    enabled_setting: ClassVar[str]
    settlement_currency: ClassVar[str | None] = None

    @property
    def is_enabled(self) -> bool:
        return bool(getattr(settings, self.enabled_setting, False))

    def prepare_amount(
        self,
        *,
        original_amount: Decimal,
        original_currency: str,
        fx_rate: Decimal | None,
        quantize: Callable[[Decimal], Decimal],
    ) -> ProviderAmount:
        currency = self.settlement_currency or original_currency
        if currency == original_currency:
            return ProviderAmount(amount=original_amount, currency=currency, fx_rate=None)
        if fx_rate is None:
            raise PaymentProviderError("exchange_rate_unavailable")
        return ProviderAmount(
            amount=quantize(original_amount * fx_rate),
            currency=currency,
            fx_rate=fx_rate,
        )

    def checkout_by_public_token(self, token) -> PaymentCheckout | None:
        if not token:
            return None
        return PaymentCheckout.objects.filter(public_token=token, provider=self.code).first()

    def checkout_by_external_id(self, external_id: str) -> PaymentCheckout | None:
        if not external_id:
            return None
        return PaymentCheckout.objects.filter(provider=self.code, external_id=external_id).first()

    @staticmethod
    def amount_minor(checkout: PaymentCheckout) -> int:
        return int(checkout.provider_amount * 100)

    @staticmethod
    def fulfill(checkout: PaymentCheckout, **kwargs) -> PaymentCheckout:
        # Runtime import keeps the provider adapters independent of booking
        # construction while still routing every callback through one service.
        from marketplace.services.booking import BookingService

        return BookingService.fulfill_checkout(checkout_id=checkout.id, **kwargs)

    def method_not_allowed(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    @abstractmethod
    def create_hosted_checkout(self, checkout: PaymentCheckout) -> HostedCheckout:
        raise NotImplementedError

    @abstractmethod
    def process_callback(self, request: HttpRequest, *, action: str | None = None) -> JsonResponse:
        raise NotImplementedError
