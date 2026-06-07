from django.urls import path

from . import views

app_name = "property"

urlpatterns = [
    path("", views.PropertyListCreateView.as_view(), name="list-create"),
    path("<int:pk>/", views.PropertyDetailView.as_view(), name="detail"),
]
