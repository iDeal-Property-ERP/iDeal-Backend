from django.urls import path

from .views import NotificationSettingsView

app_name = "notification-settings"

urlpatterns = [
    path("", NotificationSettingsView.as_view(), name="settings"),
]
