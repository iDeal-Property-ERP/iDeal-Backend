from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("acts/", views.InventoryActListCreateView.as_view(), name="act-list-create"),
    path("acts/<int:pk>/", views.InventoryActDetailView.as_view(), name="act-detail"),
    path("acts/<int:pk>/items/", views.InventoryActItemsView.as_view(), name="act-items"),
    path("acts/<int:pk>/photos/", views.InventoryActPhotosView.as_view(), name="act-photos"),
    path("acts/<int:pk>/finalize/", views.InventoryActFinalizeView.as_view(), name="act-finalize"),
]
