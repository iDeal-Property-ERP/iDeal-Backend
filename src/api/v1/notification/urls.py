from django.urls import path

from . import views

app_name = "notification"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("unread-count/", views.NotificationUnreadCountView.as_view(), name="unread-count"),
    path("read-all/", views.NotificationReadAllView.as_view(), name="read-all"),
    path("<int:pk>/read/", views.NotificationReadView.as_view(), name="read"),
]
