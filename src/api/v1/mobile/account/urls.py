from django.urls import path

from .views import (
    AccountDeletionConfirmView,
    AccountDeletionOTPRequestView,
    MobileUserAvatarView,
    MobileUserMeView,
    PhoneChangeConfirmView,
    PhoneChangeOTPRequestView,
)

app_name = "account"

urlpatterns = [
    path("me/", MobileUserMeView.as_view(), name="me"),
    path("me/avatar/", MobileUserAvatarView.as_view(), name="me-avatar"),
    path("phone/otp/request/", PhoneChangeOTPRequestView.as_view(), name="phone-otp-request"),
    path("phone/confirm/", PhoneChangeConfirmView.as_view(), name="phone-confirm"),
    path("deletion/otp/request/", AccountDeletionOTPRequestView.as_view(), name="deletion-otp-request"),
    path("deletion/confirm/", AccountDeletionConfirmView.as_view(), name="deletion-confirm"),
]
