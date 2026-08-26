from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("acts/", views.InventoryActListCreateView.as_view(), name="act-list-create"),
    path("acts/stats/", views.InventoryActStatsView.as_view(), name="act-stats"),
    path("acts/<int:pk>/", views.InventoryActDetailView.as_view(), name="act-detail"),
    path("acts/<int:pk>/acknowledge/", views.InventoryActAcknowledgeView.as_view(), name="act-acknowledge"),
]
