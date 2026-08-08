from django.urls import include, path

app_name = "mobile"

urlpatterns = [
    path("auth/", include("api.v1.mobile.auth.urls")),
    path("account/", include("api.v1.mobile.account.urls", namespace="account")),
]
