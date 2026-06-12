from django.urls import path

from . import views

app_name = "owner"

urlpatterns = [
    path("properties/", views.OwnerPropertyListView.as_view(), name="property-list"),
    path("earnings/", views.OwnerEarningsView.as_view(), name="earnings"),
    path("why/", views.OwnerWhyView.as_view(), name="why"),
]
