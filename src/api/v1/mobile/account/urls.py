from django.urls import path

from .views import MobileUserAvatarView, MobileUserMeView

app_name = "account"

urlpatterns = [
    path("me/", MobileUserMeView.as_view(), name="me"),
    path("me/avatar/", MobileUserAvatarView.as_view(), name="me-avatar"),
]
