from django.urls import path

from . import views

app_name = "contract"

urlpatterns = [
    path("owner-agreements/", views.OwnerAgreementListCreateView.as_view(), name="owner-agreement-list-create"),
    path("owner-agreements/<int:pk>/", views.OwnerAgreementDetailView.as_view(), name="owner-agreement-detail"),
    path("owner-agreements/<int:pk>/renew/", views.OwnerAgreementRenewView.as_view(), name="owner-agreement-renew"),
    path(
        "owner-agreements/<int:pk>/terminate/",
        views.OwnerAgreementTerminateView.as_view(),
        name="owner-agreement-terminate",
    ),
    path("leases/", views.LeaseListCreateView.as_view(), name="lease-list-create"),
    path("leases/<int:pk>/", views.LeaseDetailView.as_view(), name="lease-detail"),
    path("leases/<int:pk>/renew/", views.LeaseRenewView.as_view(), name="lease-renew"),
    path("leases/<int:pk>/terminate/", views.LeaseTerminateView.as_view(), name="lease-terminate"),
]
