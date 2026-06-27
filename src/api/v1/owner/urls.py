from django.urls import path

from . import views

app_name = "owner"

urlpatterns = [
    path("properties/", views.OwnerPropertyListView.as_view(), name="property-list"),
    path("earnings/", views.OwnerEarningsView.as_view(), name="earnings"),
    path("why/", views.OwnerWhyView.as_view(), name="why"),
    path("public-offer/", views.OwnerPublicOfferView.as_view(), name="public-offer"),
    path("onboarding/", views.OwnerOnboardingView.as_view(), name="onboarding"),
    # List-Your-Property wizard
    path("listings/", views.OwnerListingListCreateView.as_view(), name="listing-list-create"),
    path("listings/<int:pk>/", views.OwnerListingDetailView.as_view(), name="listing-detail"),
    path("listings/<int:pk>/photos/", views.OwnerListingPhotosView.as_view(), name="listing-photos"),
    path(
        "listings/<int:pk>/photos/reorder/", views.OwnerListingPhotoReorderView.as_view(), name="listing-photos-reorder"
    ),
    path(
        "listings/<int:pk>/photos/<int:photo_id>/",
        views.OwnerListingPhotoDeleteView.as_view(),
        name="listing-photo-delete",
    ),
    path("listings/<int:pk>/submit/", views.OwnerListingSubmitView.as_view(), name="listing-submit"),
]
