from django.urls import path

from api.v1.payment_providers.views import (
    ClickCompleteCallbackView,
    ClickPrepareCallbackView,
    PaymeCallbackView,
    StripeWebhookView,
)

app_name = "payment_providers"

urlpatterns = [
    path("payme/", PaymeCallbackView.as_view(), name="payme-callback"),
    path("click/prepare/", ClickPrepareCallbackView.as_view(), name="click-prepare"),
    path("click/complete/", ClickCompleteCallbackView.as_view(), name="click-complete"),
    path("stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
