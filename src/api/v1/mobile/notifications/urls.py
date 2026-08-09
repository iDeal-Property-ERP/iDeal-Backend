from django.urls import path

from .views import (
    MobileNotificationListView,
    MobileNotificationReadAllView,
    MobileNotificationReadView,
    MobileNotificationUnreadCountView,
)

app_name = "notifications"

urlpatterns = [
    path("", MobileNotificationListView.as_view(), name="list"),
    path("unread-count/", MobileNotificationUnreadCountView.as_view(), name="unread-count"),
    path("read-all/", MobileNotificationReadAllView.as_view(), name="read-all"),
    path("<int:pk>/read/", MobileNotificationReadView.as_view(), name="read"),
]
