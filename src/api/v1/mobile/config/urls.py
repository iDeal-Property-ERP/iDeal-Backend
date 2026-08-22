from django.urls import path

from api.v1.mobile.config.views import MobileMapConfigView, MobileVersionConfigView

app_name = "config"

urlpatterns = [
    path("map/", MobileMapConfigView.as_view(), name="map-config"),
    path("version/", MobileVersionConfigView.as_view(), name="version-config"),
]
