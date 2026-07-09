from django.urls import path

from api.v1.core.views.auth import (
    LoginAPIView,
    LogoutAPIView,
    RefreshAPIView,
    SetPasswordAPIView,
    TokenVerifyController,
)

app_name = "auth"

urlpatterns = [
    path("login/", LoginAPIView.as_view(), name="login"),
    path("refresh/", RefreshAPIView.as_view(), name="token_refresh"),
    path("verify/", TokenVerifyController.as_view(), name="token_verify"),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("set-password/", SetPasswordAPIView.as_view(), name="set_password"),
]
