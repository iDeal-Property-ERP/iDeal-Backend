from django.urls import path

from .views import MobileHomeFiltersView, MobileHomeListingsView

app_name = "home"

urlpatterns = [
    path("listings/", MobileHomeListingsView.as_view(), name="listings"),
    path("filters/", MobileHomeFiltersView.as_view(), name="filters"),
]
