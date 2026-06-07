from django.urls import path

from api.v1.core.views.auth import LoginAPIView, RefreshAPIView, TokenVerifyController

app_name = "auth"

urlpatterns = [
    path("login/", LoginAPIView.as_view(), name="login"),
    path("refresh/", RefreshAPIView.as_view(), name="token_refresh"),
    path("verify/", TokenVerifyController.as_view(), name="token_verify"),
]
