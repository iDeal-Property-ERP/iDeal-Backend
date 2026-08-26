from django.urls import path

from . import views

app_name = "owner"

urlpatterns = [
    path("properties/", views.OwnerPropertyListView.as_view(), name="property-list"),
    path("earnings/", views.OwnerEarningsView.as_view(), name="earnings"),
    path("settlements/", views.OwnerSettlementListView.as_view(), name="settlement-list"),
    path("why/", views.OwnerWhyView.as_view(), name="why"),
    path("public-offer/", views.OwnerPublicOfferView.as_view(), name="public-offer"),
    path("onboarding/", views.OwnerOnboardingView.as_view(), name="onboarding"),
    # List-Your-Property wizard
    path("listings/", views.OwnerListingListView.as_view(), name="listing-list"),
    path("listings/submit/", views.OwnerListingSubmitView.as_view(), name="listing-submit"),
    path("listings/<int:pk>/", views.OwnerListingDetailView.as_view(), name="listing-detail"),
    path("listings/<int:pk>/resubmit/", views.OwnerListingResubmitView.as_view(), name="listing-resubmit"),
]
