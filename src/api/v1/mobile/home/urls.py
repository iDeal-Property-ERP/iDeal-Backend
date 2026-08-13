from django.urls import path

from .views import (
    MobileHomeBookingOptionsView,
    MobileHomeFiltersView,
    MobileHomeListingDetailView,
    MobileHomeListingsView,
)

app_name = "home"

urlpatterns = [
    path("listings/", MobileHomeListingsView.as_view(), name="listings"),
    path("listings/<int:pk>/", MobileHomeListingDetailView.as_view(), name="listing-detail"),
    path("listings/<int:pk>/booking-options/", MobileHomeBookingOptionsView.as_view(), name="booking-options"),
    path("filters/", MobileHomeFiltersView.as_view(), name="filters"),
]
