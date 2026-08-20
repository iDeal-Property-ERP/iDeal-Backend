from django.urls import path

from .views import OTPMethodsView, OTPRequestView, OTPVerifyView

urlpatterns = [
    path("methods/", OTPMethodsView.as_view(), name="otp-methods"),
    path("otp/request/", OTPRequestView.as_view(), name="otp-request"),
    path("otp/verify/", OTPVerifyView.as_view(), name="otp-verify"),
]
