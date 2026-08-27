from django.conf import settings
from django.http import HttpRequest, JsonResponse
from marketplace.models import PaymentCheckout
from marketplace.services.payments.providers.base import HostedCheckout, PaymentProvider

from core.constants import PaymentProvider as PaymentProviderCode


class StripeProvider(PaymentProvider):
    code = PaymentProviderCode.STRIPE
    enabled_setting = "STRIPE_ENABLED"

    succeeded_events = {"checkout.session.completed", "checkout.session.async_payment_succeeded"}
    failed_events = {"checkout.session.async_payment_failed", "checkout.session.expired"}

    def create_hosted_checkout(self, checkout: PaymentCheckout) -> HostedCheckout:
        import stripe

        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = stripe.checkout.Session.create(
            mode="payment",
            client_reference_id=str(checkout.public_token),
            line_items=[
                {
                    "price_data": {
                        "currency": checkout.provider_currency.lower(),
                        "product_data": {"name": f"iDeal booking #{checkout.booking_id}"},
                        "unit_amount": self.amount_minor(checkout),
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"https://i-deal.uz/payment-return?checkout={checkout.public_token}",
            cancel_url=f"https://i-deal.uz/payment-return?checkout={checkout.public_token}",
            expires_at=int(checkout.expires_at.timestamp()),
            metadata={"checkout_id": str(checkout.id), "public_token": str(checkout.public_token)},
        )
        return HostedCheckout(url=session.url, external_id=session.id)

    def process_callback(self, request: HttpRequest, *, action: str | None = None) -> JsonResponse:
        import stripe

        try:
            event = stripe.Webhook.construct_event(
                request.body,
                request.headers.get("Stripe-Signature", ""),
                settings.STRIPE_WEBHOOK_SECRET,
            )
        except ValueError, stripe.error.SignatureVerificationError:
            return JsonResponse({"error": "invalid_signature"}, status=400)

        event_type = event["type"]
        session = event["data"]["object"]
        token = session.get("metadata", {}).get("public_token") or session.get("client_reference_id")
        checkout = self.checkout_by_public_token(token)
        if checkout is None:
            return JsonResponse({"error": "checkout_not_found"}, status=404)
        succeeded = event_type in self.succeeded_events
        failed = event_type in self.failed_events
        if not succeeded and not failed:
            return JsonResponse({"received": True})
        if succeeded and not self._amount_valid(checkout, session):
            return JsonResponse({"error": "amount_or_currency_mismatch"}, status=400)
        self.fulfill(
            checkout,
            external_event_id=event["id"],
            event_type=event_type,
            payload=dict(event),
            succeeded=succeeded,
            external_id=session.get("id"),
        )
        return JsonResponse({"received": True})

    def _amount_valid(self, checkout: PaymentCheckout, session) -> bool:
        return (
            session.get("amount_total") == self.amount_minor(checkout)
            and session.get("currency", "").upper() == checkout.provider_currency
        )
