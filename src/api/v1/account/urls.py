from django.urls import path

from .views import (
    PublicAccountDeletionChannelsView,
    PublicAccountDeletionConfirmView,
    PublicAccountDeletionOTPRequestView,
    UserMeView,
)

app_name = "account"

urlpatterns = [
    path("me/", UserMeView.as_view(), name="me"),
    path("deletion/channels/", PublicAccountDeletionChannelsView.as_view(), name="deletion-channels"),
    path("deletion/otp/request/", PublicAccountDeletionOTPRequestView.as_view(), name="deletion-otp-request"),
    path("deletion/confirm/", PublicAccountDeletionConfirmView.as_view(), name="deletion-confirm"),
]
