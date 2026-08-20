# pyright: reportMissingImports=false
from django.urls import include, path

app_name = "mobile"

urlpatterns = [
    path("auth/", include("api.v1.mobile.auth.urls")),
    path("account/", include("api.v1.mobile.account.urls", namespace="account")),
    path("favorites/", include("api.v1.mobile.favorites.urls", namespace="favorites")),
    path("home/", include("api.v1.mobile.home.urls", namespace="home")),
    path("bookings/", include("api.v1.mobile.bookings.urls", namespace="bookings")),
    path("notifications/", include("api.v1.mobile.notifications.urls", namespace="notifications")),
    path("chat/", include("api.v1.mobile.chat.urls", namespace="chat")),
    path("devices/", include("api.v1.mobile.devices.urls", namespace="devices")),
    path(
        "notification-settings/", include("api.v1.mobile.notification_settings.urls", namespace="notification-settings")
    ),
    path("support/", include("api.v1.mobile.support.urls", namespace="support")),
    path("config/", include("api.v1.mobile.config.urls", namespace="config")),
]
