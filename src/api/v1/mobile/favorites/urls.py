from django.urls import path

from .views import MobileFavoriteDetailView, MobileFavoriteListView

app_name = "favorites"

urlpatterns = [
    path("", MobileFavoriteListView.as_view(), name="list"),
    path("<int:listing_id>/", MobileFavoriteDetailView.as_view(), name="detail"),
]

