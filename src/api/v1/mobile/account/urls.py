from django.urls import path

from .views import (
    AccountDeletionConfirmView,
    AccountDeletionOTPRequestView,
    MobileUserAvatarView,
    MobileUserMeView,
)

app_name = "account"

urlpatterns = [
    path("me/", MobileUserMeView.as_view(), name="me"),
    path("me/avatar/", MobileUserAvatarView.as_view(), name="me-avatar"),
    path("deletion/otp/request/", AccountDeletionOTPRequestView.as_view(), name="deletion-otp-request"),
    path("deletion/confirm/", AccountDeletionConfirmView.as_view(), name="deletion-confirm"),
]
