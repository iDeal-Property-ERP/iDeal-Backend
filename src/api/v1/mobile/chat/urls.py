from django.urls import path

from .views import (
    ChatSummaryView,
    ConversationArchiveView,
    ConversationCollectionView,
    ConversationDetailView,
    ConversationImageMessageView,
    ConversationMessagesView,
    ConversationMuteView,
    ConversationReadView,
    ConversationReportView,
    ConversationUnarchiveView,
    ConversationUnmuteView,
)

app_name = "chat"

urlpatterns = [
    path("conversations/", ConversationCollectionView.as_view(), name="conversations"),
    path("summary/", ChatSummaryView.as_view(), name="summary"),
    path("conversations/<int:pk>/", ConversationDetailView.as_view(), name="conversation"),
    path("conversations/<int:pk>/messages/", ConversationMessagesView.as_view(), name="messages"),
    path(
        "conversations/<int:pk>/messages/image/",
        ConversationImageMessageView.as_view(),
        name="message-image",
    ),
    path("conversations/<int:pk>/read/", ConversationReadView.as_view(), name="read"),
    path("conversations/<int:pk>/archive/", ConversationArchiveView.as_view(), name="archive"),
    path("conversations/<int:pk>/unarchive/", ConversationUnarchiveView.as_view(), name="unarchive"),
    path("conversations/<int:pk>/mute/", ConversationMuteView.as_view(), name="mute"),
    path("conversations/<int:pk>/unmute/", ConversationUnmuteView.as_view(), name="unmute"),
    path("conversations/<int:pk>/report/", ConversationReportView.as_view(), name="report"),
]
