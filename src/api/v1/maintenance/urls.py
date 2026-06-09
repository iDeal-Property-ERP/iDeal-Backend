from django.urls import path

from . import views

app_name = "maintenance"

urlpatterns = [
    path("requests/", views.ServiceRequestListCreateView.as_view(), name="request-list-create"),
    path("requests/<int:pk>/", views.ServiceRequestDetailUpdateView.as_view(), name="request-detail-update"),
    path("requests/<int:pk>/assign/", views.ServiceRequestAssignView.as_view(), name="request-assign"),
    path("requests/<int:pk>/resolve/", views.ServiceRequestResolveView.as_view(), name="request-resolve"),
]
