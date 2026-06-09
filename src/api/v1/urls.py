from django.urls import include, path

app_name = "url_router"

urlpatterns = [
    path("users/", include("api.v1.account.urls", namespace="account")),
    path("auth/", include("api.v1.core.urls.auth", namespace="auth")),
    path("misc/", include("api.v1.core.urls.misc", namespace="health")),
    path("properties/", include("api.v1.property.urls", namespace="property")),
    path("contracts/", include("api.v1.contract.urls", namespace="contract")),
    path("finance/", include("api.v1.finance.urls", namespace="finance")),
    path("maintenance/", include("api.v1.maintenance.urls", namespace="maintenance")),
]
