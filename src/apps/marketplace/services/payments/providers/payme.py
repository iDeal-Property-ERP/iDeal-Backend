import base64
import hmac
import json

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from marketplace.models import PaymentCheckout, ProviderEvent
from marketplace.services.payments.providers.base import HostedCheckout, PaymentProvider

from core.constants import PaymentCheckoutStatus
from core.constants import PaymentProvider as PaymentProviderCode


class PaymeProvider(PaymentProvider):
    code = PaymentProviderCode.PAYME
    enabled_setting = "PAYME_ENABLED"
    settlement_currency = "UZS"

    def create_hosted_checkout(self, checkout: PaymentCheckout) -> HostedCheckout:
        params = (
            f"m={settings.PAYME_MERCHANT_ID};"
            f"ac.checkout={checkout.public_token};"
            f"a={self.amount_minor(checkout)}"
        )
        encoded = base64.b64encode(params.encode()).decode()
        return HostedCheckout(url=f"{settings.PAYME_CHECKOUT_URL.rstrip('/')}/{encoded}")

    def process_callback(self, request: HttpRequest, *, action: str | None = None) -> JsonResponse:
        if not self._auth_valid(request):
            return self._error(None, -32504, "Insufficient privilege")
        try:
            body = json.loads(request.body)
        except (TypeError, ValueError):
            return self._error(None, -32700, "Parse error")

        request_id = body.get("id")
        method = body.get("method")
        params = body.get("params") or {}
        handler = {
            "CheckPerformTransaction": self._check_perform,
            "CreateTransaction": self._create_transaction,
            "PerformTransaction": self._perform_transaction,
            "CancelTransaction": self._cancel_transaction,
            "CheckTransaction": self._check_transaction,
            "GetStatement": self._get_statement,
        }.get(method)
        if handler is None:
            return self._error(request_id, -32601, "Method not found")
        return handler(request_id, params, body)

    def method_not_allowed(self, request: HttpRequest) -> JsonResponse:
        return self._error(None, -32504, "Insufficient privilege")

    @staticmethod
    def _error(request_id, code: int, message: str, data=None) -> JsonResponse:
        error = {"code": code, "message": {"ru": message, "uz": message, "en": message}}
        if data:
            error["data"] = data
        return JsonResponse({"jsonrpc": "2.0", "id": request_id, "error": error})

    @staticmethod
    def _result(request_id, result: dict) -> JsonResponse:
        return JsonResponse({"jsonrpc": "2.0", "id": request_id, "result": result})

    @staticmethod
    def _auth_valid(request: HttpRequest) -> bool:
        try:
            scheme, encoded = request.headers.get("Authorization", "").split(" ", 1)
            login, key = base64.b64decode(encoded).decode().split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return False
        return scheme.lower() == "basic" and login == "Paycom" and hmac.compare_digest(key, settings.PAYME_KEY)

    def _checkout(self, params) -> PaymentCheckout | None:
        return self.checkout_by_public_token(params.get("account", {}).get("checkout"))

    def _transaction_checkout(self, params) -> PaymentCheckout | None:
        checkout = self._checkout(params)
        return checkout or self.checkout_by_external_id(str(params.get("id", "")))

    def _amount_valid(self, checkout: PaymentCheckout | None, params) -> bool:
        if checkout is None:
            return False
        try:
            return self.amount_minor(checkout) == int(params.get("amount", -1))
        except (TypeError, ValueError):
            return False

    def _check_perform(self, request_id, params, body) -> JsonResponse:
        checkout = self._checkout(params)
        if checkout is None:
            return self._error(request_id, -31050, "Checkout not found", "checkout")
        if not self._amount_valid(checkout, params):
            return self._error(request_id, -31001, "Invalid amount")
        return self._result(request_id, {"allow": True})

    def _create_transaction(self, request_id, params, body) -> JsonResponse:
        checkout = self._checkout(params)
        payme_id = str(params.get("id", ""))
        if checkout is None:
            return self._error(request_id, -31050, "Checkout not found", "checkout")
        if not self._amount_valid(checkout, params):
            return self._error(request_id, -31001, "Invalid amount")
        if checkout.status != PaymentCheckoutStatus.PENDING or (
            checkout.external_id and checkout.external_id != payme_id
        ):
            return self._error(request_id, -31008, "Operation cannot be performed")

        checkout.external_id = payme_id
        checkout.save(update_fields=["external_id", "updated_at"])
        ProviderEvent.objects.get_or_create(
            provider=self.code,
            external_event_id=f"create:{payme_id}",
            defaults={
                "checkout": checkout,
                "event_type": "CreateTransaction",
                "payload": body,
                "result": {"state": 1},
            },
        )
        return self._result(
            request_id,
            {
                "create_time": int(checkout.created_at.timestamp() * 1000),
                "transaction": str(checkout.id),
                "state": 1,
            },
        )

    def _perform_transaction(self, request_id, params, body) -> JsonResponse:
        checkout = self._transaction_checkout(params)
        payme_id = str(params.get("id", ""))
        if checkout is None:
            return self._error(request_id, -31003, "Transaction not found")
        checkout = self.fulfill(
            checkout,
            external_event_id=f"perform:{payme_id}",
            event_type="PerformTransaction",
            payload=body,
            succeeded=True,
            external_id=payme_id,
        )
        state = 2 if checkout.status == PaymentCheckoutStatus.SUCCEEDED else -1
        return self._result(
            request_id,
            {
                "transaction": str(checkout.id),
                "perform_time": int((checkout.completed_at or timezone.now()).timestamp() * 1000),
                "state": state,
            },
        )

    def _cancel_transaction(self, request_id, params, body) -> JsonResponse:
        checkout = self._transaction_checkout(params)
        payme_id = str(params.get("id", ""))
        if checkout is None:
            return self._error(request_id, -31003, "Transaction not found")
        if checkout.status == PaymentCheckoutStatus.SUCCEEDED:
            return self._error(request_id, -31007, "Order already fulfilled")
        checkout = self.fulfill(
            checkout,
            external_event_id=f"cancel:{payme_id}:{params.get('reason')}",
            event_type="CancelTransaction",
            payload=body,
            succeeded=False,
        )
        return self._result(
            request_id,
            {
                "transaction": str(checkout.id),
                "cancel_time": int(timezone.now().timestamp() * 1000),
                "state": -1,
            },
        )

    def _check_transaction(self, request_id, params, body) -> JsonResponse:
        checkout = self._transaction_checkout(params)
        if checkout is None:
            return self._error(request_id, -31003, "Transaction not found")
        state = {
            PaymentCheckoutStatus.PENDING: 1,
            PaymentCheckoutStatus.SUCCEEDED: 2,
            PaymentCheckoutStatus.FAILED: -1,
            PaymentCheckoutStatus.EXPIRED: -1,
        }.get(checkout.status, -2)
        return self._result(
            request_id,
            {
                "create_time": int(checkout.created_at.timestamp() * 1000),
                "perform_time": int(checkout.completed_at.timestamp() * 1000) if checkout.completed_at else 0,
                "cancel_time": 0,
                "transaction": str(checkout.id),
                "state": state,
                "reason": None,
            },
        )

    def _get_statement(self, request_id, params, body) -> JsonResponse:
        try:
            from_timestamp = int(params["from"])
            to_timestamp = int(params["to"])
        except (KeyError, TypeError, ValueError):
            return self._error(request_id, -32602, "Invalid params")
        if from_timestamp > to_timestamp:
            return self._error(request_id, -32602, "Invalid params")
        events = (
            ProviderEvent.objects.filter(
                provider=self.code,
                event_type="CreateTransaction",
                payload__params__time__gte=from_timestamp,
                payload__params__time__lte=to_timestamp,
            )
            .select_related("checkout")
            .order_by("payload__params__time", "created_at")
        )
        return self._result(request_id, {"transactions": [self._transaction(event) for event in events]})

    def _transaction(self, event: ProviderEvent) -> dict:
        checkout = event.checkout
        params = event.payload.get("params", {})
        created_at = int(params.get("time") or checkout.created_at.timestamp() * 1000)
        completed_at = int(checkout.completed_at.timestamp() * 1000) if checkout.completed_at else 0
        succeeded = checkout.status == PaymentCheckoutStatus.SUCCEEDED
        cancelled = checkout.status in {PaymentCheckoutStatus.FAILED, PaymentCheckoutStatus.EXPIRED}
        return {
            "id": checkout.external_id or str(params.get("id", "")),
            "time": created_at,
            "amount": self.amount_minor(checkout),
            "account": {"checkout": str(checkout.public_token)},
            "create_time": created_at,
            "perform_time": completed_at if succeeded else 0,
            "cancel_time": completed_at if cancelled else 0,
            "transaction": str(checkout.id),
            "state": 2 if succeeded else (-1 if cancelled else 1),
            "reason": None,
            "receivers": None,
        }
