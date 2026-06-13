from django.urls import path

from . import views

app_name = "management"

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("pnl/", views.PnLSummaryView.as_view(), name="pnl"),
    path("users/", views.ManagementUserListView.as_view(), name="user-list"),
    path("users/<int:pk>/", views.ManagementUserDetailUpdateView.as_view(), name="user-detail"),
    path("properties/", views.ManagementPropertyListView.as_view(), name="property-list"),
    path("leases/", views.LeaseListView.as_view(), name="lease-list"),
    path("owner-agreements/", views.OwnerAgreementListView.as_view(), name="owner-agreement-list"),
    path("payments/", views.PaymentListView.as_view(), name="payment-list"),
    path("payouts/", views.PayoutListView.as_view(), name="payout-list"),
    path("service-requests/", views.ManagementServiceRequestListView.as_view(), name="service-request-list"),
]
