from django.urls import path

from . import views

app_name = "tenant"

urlpatterns = [
    path("home/", views.TenantHomeView.as_view(), name="home"),
    path("payments/", views.TenantPaymentListCreateView.as_view(), name="payment-list-create"),
    path("service-requests/", views.TenantServiceRequestListCreateView.as_view(), name="sr-list-create"),
]
