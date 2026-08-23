from django.urls import path

from .views import MobileContractListView

app_name = "contracts"

urlpatterns = [
    path("", MobileContractListView.as_view(), name="list"),
]
