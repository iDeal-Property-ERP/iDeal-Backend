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
    path("marketplace/", include("api.v1.marketplace.urls", namespace="marketplace")),
    path("agents/", include("api.v1.agent.urls", namespace="agent")),
    path("owner/", include("api.v1.owner.urls", namespace="owner")),
    path("tenant/", include("api.v1.tenant.urls", namespace="tenant")),
    path("management/", include("api.v1.management.urls", namespace="management")),
    path("notifications/", include("api.v1.notification.urls", namespace="notification")),
    path("inventory/", include("api.v1.inventory.urls", namespace="inventory")),
    path("vas/", include("api.v1.vas.urls", namespace="vas")),
]
