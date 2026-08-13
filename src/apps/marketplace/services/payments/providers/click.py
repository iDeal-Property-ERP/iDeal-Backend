import hashlib
import hmac
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from marketplace.models import PaymentCheckout, ProviderEvent
from marketplace.services.payments.providers.base import HostedCheckout, PaymentProvider

from core.constants import PaymentCheckoutStatus
from core.constants import PaymentProvider as PaymentProviderCode


class ClickProvider(PaymentProvider):
    code = PaymentProviderCode.CLICK
    enabled_setting = "CLICK_ENABLED"
    settlement_currency = "UZS"

    def create_hosted_checkout(self, checkout: PaymentCheckout) -> HostedCheckout:
        params = urlencode(
            {
                "service_id": settings.CLICK_SERVICE_ID,
                "merchant_id": settings.CLICK_MERCHANT_ID,
                "amount": checkout.provider_amount,
                "transaction_param": checkout.public_token,
                "return_url": f"https://i-deal.uz/payment-return?checkout={checkout.public_token}",
            }
        )
        return HostedCheckout(url=f"{settings.CLICK_CHECKOUT_URL}?{params}")

    def process_callback(self, request: HttpRequest, *, action: str | None = None) -> JsonResponse:
        params = request.POST.dict()
        if action not in {"prepare", "complete"}:
            return self._response(params, -3, "ACTION NOT FOUND")
        complete = action == "complete"
        if not self._signature_valid(params, complete=complete):
            return self._response(params, -1, "SIGN CHECK FAILED")
        return self._complete(params) if complete else self._prepare(params)

    def method_not_allowed(self, request: HttpRequest) -> JsonResponse:
        return self._response({}, -3, "ACTION NOT FOUND")

    @staticmethod
    def _response(params, error: int, note: str, checkout=None) -> JsonResponse:
        data = {
            "click_trans_id": params.get("click_trans_id"),
            "merchant_trans_id": params.get("merchant_trans_id"),
            "error": error,
            "error_note": note,
        }
        if checkout:
            data["merchant_prepare_id"] = checkout.id
            data["merchant_confirm_id"] = checkout.id
        return JsonResponse(data)

    @staticmethod
    def _signature_valid(params, *, complete: bool) -> bool:
        parts = [
            params.get("click_trans_id", ""),
            params.get("service_id", ""),
            settings.CLICK_SECRET_KEY,
            params.get("merchant_trans_id", ""),
        ]
        if complete:
            parts.append(params.get("merchant_prepare_id", ""))
        parts.extend([params.get("amount", ""), params.get("action", ""), params.get("sign_time", "")])
        expected = hashlib.md5("".join(map(str, parts)).encode(), usedforsecurity=False).hexdigest()
        return hmac.compare_digest(expected, params.get("sign_string", ""))

    def _checkout(self, params) -> PaymentCheckout | None:
        return self.checkout_by_public_token(params.get("merchant_trans_id"))

    @staticmethod
    def _amount_valid(checkout: PaymentCheckout, params) -> bool:
        try:
            return Decimal(params.get("amount", "-1")) == checkout.provider_amount
        except InvalidOperation:
            return False

    def _prepare(self, params) -> JsonResponse:
        checkout = self._checkout(params)
        if checkout is None:
            return self._response(params, -5, "USER DOES NOT EXIST")
        if not self._amount_valid(checkout, params):
            return self._response(params, -2, "INCORRECT PARAMETER AMOUNT")
        if checkout.status != PaymentCheckoutStatus.PENDING:
            return self._response(params, -4, "ALREADY PAID")
        checkout.external_id = params.get("click_trans_id")
        checkout.save(update_fields=["external_id", "updated_at"])
        ProviderEvent.objects.get_or_create(
            provider=self.code,
            external_event_id=f"prepare:{params.get('click_trans_id')}",
            defaults={"checkout": checkout, "event_type": "Prepare", "payload": params, "result": {"error": 0}},
        )
        return self._response(params, 0, "Success", checkout)

    def _complete(self, params) -> JsonResponse:
        checkout = self._checkout(params)
        if checkout is None or str(checkout.id) != params.get("merchant_prepare_id"):
            return self._response(params, -6, "TRANSACTION DOES NOT EXIST")
        if not self._amount_valid(checkout, params):
            return self._response(params, -2, "INCORRECT PARAMETER AMOUNT")
        succeeded = params.get("error") == "0"
        checkout = self.fulfill(
            checkout,
            external_event_id=f"complete:{params.get('click_trans_id')}:{params.get('error')}",
            event_type="Complete",
            payload=params,
            succeeded=succeeded,
            external_id=params.get("click_trans_id"),
        )
        return self._response(
            params,
            0 if succeeded else -9,
            "Success" if succeeded else "Transaction cancelled",
            checkout,
        )
