from django.urls import path

from .views import DeviceRegistrationView, DeviceUnregisterView

app_name = "devices"

urlpatterns = [
    path("", DeviceRegistrationView.as_view(), name="register"),
    path("unregister/", DeviceUnregisterView.as_view(), name="unregister"),
]
