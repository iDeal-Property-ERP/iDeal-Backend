from django.urls import path

from . import views

app_name = "vas"

urlpatterns = [
    path("catalog/", views.ServiceCatalogListCreateView.as_view(), name="catalog-list-create"),
    path("catalog/<int:pk>/", views.ServiceCatalogDetailView.as_view(), name="catalog-detail"),
]
