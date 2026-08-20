from django.urls import path

from api.v1.mobile.config.views import MobileMapConfigView

app_name = "config"

urlpatterns = [
    path("map/", MobileMapConfigView.as_view(), name="map-config"),
]
