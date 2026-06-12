from django.urls import path

from . import views

app_name = "marketplace"

urlpatterns = [
    path("listings/", views.ListingListView.as_view(), name="listing-list"),
    path("listings/map/", views.ListingMapView.as_view(), name="listing-map"),
    path("listings/<int:pk>/", views.ListingDetailView.as_view(), name="listing-detail"),
    path("listings/<int:pk>/book-viewing/", views.BookViewingView.as_view(), name="listing-book-viewing"),
]
