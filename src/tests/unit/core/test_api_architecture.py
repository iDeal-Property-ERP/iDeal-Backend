"""Ratchet tests for the architecture slices migrated in this change.

The complete repository is intentionally not grandfathered as compliant: each
migrated context is protected here while the audit records the remaining work.
"""

import inspect

from marketplace.services.favorites import FavoriteListingService
from marketplace.services.listings import ListingDiscoveryService, ListingFilterSet
from marketplace.services.recommendations import RecommendationService

from api.v1.management.views import (
    OneOffCommissionReceiptAttachmentView,
    OneOffCommissionReceiptView,
    OneOffDealActivateView,
    OneOffDealArchiveView,
    OneOffDealCloseLostView,
    OneOffDealCloseWonView,
    OneOffDealPauseView,
)
from core.api.filters import PydanticFilterSet
from core.api.views import ListAPIView


def test_one_off_action_controllers_expose_post_only():
    action_views = (
        OneOffDealActivateView,
        OneOffDealPauseView,
        OneOffDealCloseWonView,
        OneOffDealCloseLostView,
        OneOffDealArchiveView,
        OneOffCommissionReceiptView,
        OneOffCommissionReceiptAttachmentView,
    )
    for view in action_views:
        assert set(view.api_endpoints) == {"POST"}


def test_migrated_services_are_real_instances_not_static_namespaces():
    for service in (RecommendationService, FavoriteListingService, ListingDiscoveryService):
        assert "__init__" in service.__dict__
        static_or_class_methods = [
            name
            for name, value in service.__dict__.items()
            if isinstance(value, staticmethod | classmethod) and not name.startswith("_")
        ]
        assert static_or_class_methods == []


def test_migrated_listing_filter_uses_the_query_model_adapter():
    assert issubclass(ListingFilterSet, PydanticFilterSet)
    assert "filter_queryset" in ListingFilterSet.__dict__


def test_generic_list_paginates_before_output_conversion():
    source = inspect.getsource(ListAPIView.get)
    assert "list_response" in source
    assert "[self.to_output" not in source
