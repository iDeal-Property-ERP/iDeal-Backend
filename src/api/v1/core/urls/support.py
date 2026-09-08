from django.urls import path

from api.v1.core.views.support import SupportInquiryCreateView

app_name = "support"

urlpatterns = [
    path("inquiries/", SupportInquiryCreateView.as_view(), name="inquiry-create"),
]
