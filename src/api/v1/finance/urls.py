from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("payments/", views.PaymentListCreateView.as_view(), name="payment-list-create"),
    path("payments/<int:pk>/", views.PaymentPartialUpdateView.as_view(), name="payment-partial-update"),
    path("payments/<int:pk>/mark-paid/", views.PaymentMarkPaidView.as_view(), name="payment-mark-paid"),
    path("payouts/", views.PayoutScheduleListView.as_view(), name="payout-list"),
    path("exchange-rates/", views.ExchangeRateListCreateView.as_view(), name="exchange-rate-list-create"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("pnl/", views.PnLView.as_view(), name="pnl"),
]
