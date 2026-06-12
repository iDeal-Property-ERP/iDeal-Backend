from django.urls import path

from . import views

app_name = "agent"

urlpatterns = [
    path("", views.AgentListView.as_view(), name="agent-list"),
    path("<int:pk>/", views.AgentDetailView.as_view(), name="agent-detail"),
    path("<int:pk>/deals/", views.AgentDealListCreateView.as_view(), name="agent-deal-list-create"),
]
