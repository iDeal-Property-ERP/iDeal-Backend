from django.urls import path

from api.v1.mobile.bookings.views import (
    MobileBookingCheckoutView,
    MobileBookingDetailView,
    MobileBookingListView,
    MobileBookingQuoteView,
)

app_name = "bookings"

urlpatterns = [
    path("", MobileBookingListView.as_view(), name="list"),
    path("quotes/", MobileBookingQuoteView.as_view(), name="quote"),
    path("checkouts/", MobileBookingCheckoutView.as_view(), name="checkout"),
    path("<int:pk>/", MobileBookingDetailView.as_view(), name="detail"),
]
