from django.urls import path

from . import views

app_name = "property"

urlpatterns = [
    path("", views.PropertyListCreateView.as_view(), name="list-create"),
    path("drafts/", views.PropertyDraftCreateView.as_view(), name="draft-create"),
    path("one-off-drafts/", views.OneOffPropertyDraftView.as_view(), name="one-off-draft-create"),
    path("<int:pk>/one-off/", views.OneOffPropertyUpdateView.as_view(), name="one-off-update"),
    path("<int:pk>/", views.PropertyDetailView.as_view(), name="detail"),
    path("<int:pk>/publish/", views.PropertyPublishView.as_view(), name="publish"),
    path("<int:pk>/photos/", views.PropertyPhotosView.as_view(), name="photos"),
    path("<int:pk>/photos/reorder/", views.PropertyPhotoReorderView.as_view(), name="photos-reorder"),
    path("<int:pk>/photos/<int:photo_id>/", views.PropertyPhotoDeleteView.as_view(), name="photo-delete"),
    path(
        "<int:pk>/verification-visits/",
        views.PropertyVerificationVisitView.as_view(),
        name="verification-visits",
    ),
]
