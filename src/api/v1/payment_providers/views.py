from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from marketplace.services.payments.providers import ClickProvider, PaymentProvider, PaymeProvider, StripeProvider


@method_decorator(csrf_exempt, name="dispatch")
class PaymentProviderCallbackView(View):
    """Thin unauthenticated transport adapter for provider-owned protocols."""

    http_method_names = ["post"]
    provider_class: type[PaymentProvider]
    callback_action: str | None = None

    def get_provider(self) -> PaymentProvider:
        return self.provider_class()

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.get_provider().process_callback(request, action=self.callback_action)

    def http_method_not_allowed(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.get_provider().method_not_allowed(request)


class PaymeCallbackView(PaymentProviderCallbackView):
    provider_class = PaymeProvider


class ClickCallbackView(PaymentProviderCallbackView):
    provider_class = ClickProvider


class ClickPrepareCallbackView(ClickCallbackView):
    callback_action = "prepare"


class ClickCompleteCallbackView(ClickCallbackView):
    callback_action = "complete"


class StripeWebhookView(PaymentProviderCallbackView):
    provider_class = StripeProvider
