from django.urls import path

from . import views

app_name = "management"

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("pnl/", views.PnLSummaryView.as_view(), name="pnl"),
    path("users/", views.ManagementUserListView.as_view(), name="user-list"),
    path("users/invite/", views.ManagementUserInviteView.as_view(), name="user-invite"),
    path("users/<int:pk>/", views.ManagementUserDetailUpdateView.as_view(), name="user-detail"),
    path("properties/", views.ManagementPropertyListView.as_view(), name="property-list"),
    path("leases/", views.LeaseListView.as_view(), name="lease-list"),
    path("owner-agreements/", views.OwnerAgreementListView.as_view(), name="owner-agreement-list"),
    path("payments/", views.PaymentListView.as_view(), name="payment-list"),
    path("payments/stats/", views.PaymentStatsView.as_view(), name="payment-stats"),
    path("payouts/", views.PayoutListView.as_view(), name="payout-list"),
    path("payouts/stats/", views.PayoutStatsView.as_view(), name="payout-stats"),
    path("service-requests/", views.ManagementServiceRequestListView.as_view(), name="service-request-list"),
    path("onboardings/", views.ManagementOnboardingListView.as_view(), name="onboarding-list"),
    path("onboardings/<int:pk>/approve/", views.ManagementOnboardingApproveView.as_view(), name="onboarding-approve"),
    path("onboardings/<int:pk>/reject/", views.ManagementOnboardingRejectView.as_view(), name="onboarding-reject"),
    path("bookings/", views.ManagementBookingListView.as_view(), name="booking-list"),
    path("bookings/<int:pk>/approve/", views.ManagementBookingApproveView.as_view(), name="booking-approve"),
    path("bookings/<int:pk>/reject/", views.ManagementBookingRejectView.as_view(), name="booking-reject"),
    path("bookings/<int:pk>/convert/", views.ManagementBookingConvertView.as_view(), name="booking-convert"),
    path("viewing-requests/", views.ManagementViewingRequestListView.as_view(), name="viewing-request-list"),
    path(
        "viewing-requests/<int:pk>/confirm/",
        views.ManagementViewingRequestConfirmView.as_view(),
        name="viewing-request-confirm",
    ),
    path(
        "viewing-requests/<int:pk>/cancel/",
        views.ManagementViewingRequestCancelView.as_view(),
        name="viewing-request-cancel",
    ),
    path("vas-orders/", views.ManagementVASOrderListView.as_view(), name="vas-order-list"),
    path("vas-orders/<int:pk>/status/", views.ManagementVASOrderStatusView.as_view(), name="vas-order-status"),
    path("vacancy/", views.ManagementVacancyView.as_view(), name="vacancy"),
]
