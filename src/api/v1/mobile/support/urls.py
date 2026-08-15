# pi-lens-ignore: reportMissingImports
from django.urls import path

from api.v1.mobile.support.views import MobileSupportLinksView

app_name = "support"

urlpatterns = [
    path("links/", MobileSupportLinksView.as_view(), name="links"),
]
