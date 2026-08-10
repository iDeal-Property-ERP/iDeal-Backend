from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("conversations/", views.ConversationListView.as_view(), name="conversation-list"),
    path("conversations/<int:pk>/", views.ConversationDetailView.as_view(), name="conversation-detail"),
    path("conversations/<int:pk>/messages/", views.ConversationMessagesView.as_view(), name="message-list"),
    path(
        "conversations/<int:pk>/messages/image/",
        views.ConversationImageMessageCreateView.as_view(),
        name="message-image-create",
    ),
    path("conversations/<int:pk>/read/", views.ConversationReadView.as_view(), name="conversation-read"),
    path("conversations/<int:pk>/archive/", views.ConversationArchiveView.as_view(), name="conversation-archive"),
    path(
        "conversations/<int:pk>/unarchive/",
        views.ConversationUnarchiveView.as_view(),
        name="conversation-unarchive",
    ),
    path("conversations/<int:pk>/block/", views.ConversationBlockView.as_view(), name="conversation-block"),
    path("conversations/<int:pk>/unblock/", views.ConversationUnblockView.as_view(), name="conversation-unblock"),
    path("reports/", views.ReportListView.as_view(), name="report-list"),
    path("reports/<int:pk>/resolve/", views.ReportResolveView.as_view(), name="report-resolve"),
]
