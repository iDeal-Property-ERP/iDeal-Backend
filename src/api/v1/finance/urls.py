from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("payments/", views.PaymentListCreateView.as_view(), name="payment-list-create"),
    path("payments/bulk-mark-paid/", views.PaymentBulkMarkPaidView.as_view(), name="payment-bulk-mark-paid"),
    path("payments/bulk-remind/", views.PaymentBulkRemindView.as_view(), name="payment-bulk-remind"),
    path("payments/<int:pk>/", views.PaymentPartialUpdateView.as_view(), name="payment-partial-update"),
    path("payments/<int:pk>/mark-paid/", views.PaymentMarkPaidView.as_view(), name="payment-mark-paid"),
    path("payments/<int:pk>/remind/", views.PaymentRemindView.as_view(), name="payment-remind"),
    path("settlements/", views.SettlementListView.as_view(), name="settlement-list"),
    path("settlements/<int:pk>/", views.SettlementDetailView.as_view(), name="settlement-detail"),
    path("settlements/<int:pk>/allocations/", views.SettlementAllocationsView.as_view(), name="settlement-allocations"),
    path("payouts/", views.PayoutScheduleListCreateView.as_view(), name="payout-list-create"),
    path("payouts/bulk-mark-paid/", views.PayoutScheduleBulkMarkPaidView.as_view(), name="payout-bulk-mark-paid"),
    path("payouts/<int:pk>/", views.PayoutScheduleDetailView.as_view(), name="payout-detail"),
    path("payouts/<int:pk>/mark-paid/", views.PayoutScheduleMarkPaidView.as_view(), name="payout-mark-paid"),
    path("payouts/<int:pk>/hold/", views.PayoutScheduleHoldView.as_view(), name="payout-hold"),
    path("payouts/<int:pk>/release/", views.PayoutScheduleReleaseView.as_view(), name="payout-release"),
    path("payouts/<int:pk>/cancel/", views.PayoutScheduleCancelView.as_view(), name="payout-cancel"),
    path("exchange-rates/", views.ExchangeRateListCreateView.as_view(), name="exchange-rate-list-create"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("pnl/", views.PnLView.as_view(), name="pnl"),
]
