from django.urls import path

from .views import MobilePropertyUploadConfigView, MobilePropertyUploadSubmitView

app_name = "property-upload"

urlpatterns = [
    path("config/", MobilePropertyUploadConfigView.as_view(), name="config"),
    path("submit/", MobilePropertyUploadSubmitView.as_view(), name="submit"),
]
