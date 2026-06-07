from django.urls import path

from . import views

app_name = "contract"

urlpatterns = [
    path("owner-agreements/", views.OwnerAgreementListCreateView.as_view(), name="owner-agreement-list-create"),
    path("leases/", views.LeaseListCreateView.as_view(), name="lease-list-create"),
    path("leases/<int:pk>/", views.LeaseDetailView.as_view(), name="lease-detail"),
    path("leases/<int:pk>/renew/", views.LeaseRenewView.as_view(), name="lease-renew"),
]
