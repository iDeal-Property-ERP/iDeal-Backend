from django.urls import path

from .views import MobileMyListingsListView, MobileMyListingsStatsView

app_name = "my_listings"

urlpatterns = [
    path("", MobileMyListingsListView.as_view(), name="list"),
    path("stats/", MobileMyListingsStatsView.as_view(), name="stats"),
]
