from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone
from marketplace.models import FavoriteListing

from core.constants import ListingStatus, PropertyEngagementType, PropertyStatus
from tests.factories import (
    FavoriteListingFactory,
    ListingFactory,
    OwnerAgreementFactory,
    PropertyFactory,
    TenantFactory,
)

pytestmark = pytest.mark.django_db

FAVORITES_URL = "/api/v1/mobile/favorites/"


def _make_jwt(user):
    from datetime import UTC, datetime, timedelta

    import jwt

    payload = {
        "sub": str(user.id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _visible_listing(**property_kwargs):
    property_obj = PropertyFactory(status=PropertyStatus.VACANT, **property_kwargs)
    return property_obj.listing


class TestMobileFavoritesList:
    @pytest.mark.parametrize(
        ("method", "path", "extra_kwargs"),
        [
            ("get", FAVORITES_URL, {}),
            ("put", f"{FAVORITES_URL}1/", {"content_type": "application/json"}),
            ("delete", f"{FAVORITES_URL}1/", {}),
        ],
    )
    def test_requires_authentication(self, api_client, method, path, extra_kwargs):
        response = getattr(api_client, method)(path, **extra_kwargs)

        assert response.status_code == 401

    def test_list_isolated_to_authenticated_user(self, api_client):
        tenant = TenantFactory()
        other_tenant = TenantFactory()
        own_listing = _visible_listing()
        other_listing = _visible_listing()
        FavoriteListingFactory(user=tenant, listing=own_listing)
        FavoriteListingFactory(user=other_tenant, listing=other_listing)

        response = api_client.get(FAVORITES_URL, **_make_jwt(tenant))

        assert response.status_code == 200
        returned_ids = {item["id"] for item in response.json()["data"]["page"]["object_list"]}
        assert returned_ids == {own_listing.id}

    def test_orders_by_most_recent_like_and_omits_ineligible_rows(self, api_client, mocker):
        tenant = TenantFactory()
        mocker.patch("marketplace.services.booking.BookingService.enabled_providers", return_value=["click"])
        oldest = FavoriteListingFactory(user=tenant, listing=_visible_listing())
        newest = FavoriteListingFactory(user=tenant, listing=_visible_listing())

        hidden_listing = _visible_listing()
        hidden_listing.status = ListingStatus.DRAFT
        hidden_listing.save(update_fields=["status", "updated_at"])
        FavoriteListingFactory(user=tenant, listing=hidden_listing)

        future_property = PropertyFactory(
            status=PropertyStatus.RENTED,
            engagement_type=PropertyEngagementType.MANAGED,
            is_verified=True,
        )
        future_listing = ListingFactory(property=future_property, status=ListingStatus.PUBLISHED)
        OwnerAgreementFactory(
            property=future_property,
            owner=future_property.owner,
            start_date=timezone.localdate() - timedelta(days=15),
            end_date=timezone.localdate() + timedelta(days=15),
        )
        middle = FavoriteListingFactory(user=tenant, listing=future_listing)

        FavoriteListing.objects.filter(pk=oldest.pk).update(created_at=timezone.now() - timedelta(days=3))
        FavoriteListing.objects.filter(pk=middle.pk).update(created_at=timezone.now() - timedelta(days=2))
        FavoriteListing.objects.filter(pk=newest.pk).update(created_at=timezone.now() - timedelta(days=1))

        response = api_client.get(FAVORITES_URL, **_make_jwt(tenant))

        assert response.status_code == 200
        items = response.json()["data"]["page"]["object_list"]
        assert [item["id"] for item in items] == [newest.listing_id, future_listing.id, oldest.listing_id]
        assert hidden_listing.id not in {item["id"] for item in items}
        assert all(item["is_favorite"] is True for item in items)

    def test_pagination_slices_ordered_favorites(self, api_client):
        tenant = TenantFactory()
        favorites = [FavoriteListingFactory(user=tenant, listing=_visible_listing()) for _ in range(3)]
        for index, favorite in enumerate(favorites, start=1):
            FavoriteListing.objects.filter(pk=favorite.pk).update(created_at=timezone.now() - timedelta(days=index))

        response = api_client.get(FAVORITES_URL, {"page": 2, "per_page": 1}, **_make_jwt(tenant))

        assert response.status_code == 200
        assert response.json()["data"]["num_pages"] == 3
        assert len(response.json()["data"]["page"]["object_list"]) == 1

    def test_omits_each_requested_ineligible_state_without_deleting_relations(self, api_client, mocker):
        tenant = TenantFactory()
        mocker.patch("marketplace.services.booking.BookingService.enabled_providers", return_value=["click"])

        visible = FavoriteListingFactory(user=tenant, listing=_visible_listing())

        draft_listing = _visible_listing()
        draft_listing.status = ListingStatus.DRAFT
        draft_listing.save(update_fields=["status", "updated_at"])
        draft_favorite = FavoriteListingFactory(user=tenant, listing=draft_listing)

        rented_listing = ListingFactory(property=PropertyFactory(status=PropertyStatus.RENTED), status=ListingStatus.PUBLISHED)
        rented_favorite = FavoriteListingFactory(user=tenant, listing=rented_listing)

        soft_deleted_listing = _visible_listing()
        soft_deleted_favorite = FavoriteListingFactory(user=tenant, listing=soft_deleted_listing)
        soft_deleted_listing.delete()

        managed_without_agreement_property = PropertyFactory(
            status=PropertyStatus.RENTED,
            engagement_type=PropertyEngagementType.MANAGED,
            is_verified=True,
        )
        managed_without_agreement = ListingFactory(
            property=managed_without_agreement_property,
            status=ListingStatus.PUBLISHED,
        )
        managed_without_agreement_favorite = FavoriteListingFactory(user=tenant, listing=managed_without_agreement)

        eligible_future_property = PropertyFactory(
            status=PropertyStatus.RENTED,
            engagement_type=PropertyEngagementType.MANAGED,
            is_verified=True,
        )
        OwnerAgreementFactory(
            property=eligible_future_property,
            owner=eligible_future_property.owner,
            start_date=timezone.localdate() - timedelta(days=15),
            end_date=timezone.localdate() + timedelta(days=15),
        )
        eligible_future_listing = ListingFactory(property=eligible_future_property, status=ListingStatus.PUBLISHED)
        eligible_future_favorite = FavoriteListingFactory(user=tenant, listing=eligible_future_listing)

        response = api_client.get(FAVORITES_URL, **_make_jwt(tenant))

        assert response.status_code == 200
        returned_ids = {item["id"] for item in response.json()["data"]["page"]["object_list"]}
        assert returned_ids == {visible.listing_id, eligible_future_listing.id}
        assert draft_listing.id not in returned_ids
        assert rented_listing.id not in returned_ids
        assert soft_deleted_listing.id not in returned_ids
        assert managed_without_agreement.id not in returned_ids
        assert FavoriteListing.objects.filter(
            pk__in=[
                draft_favorite.pk,
                rented_favorite.pk,
                managed_without_agreement_favorite.pk,
                eligible_future_favorite.pk,
            ]
        ).count() == 4
        assert FavoriteListing.global_objects.filter(pk=soft_deleted_favorite.pk).exists()


class TestMobileFavoriteToggle:
    def test_put_favorites_visible_listing_and_is_idempotent(self, api_client):
        tenant = TenantFactory()
        listing = _visible_listing()

        first = api_client.put(f"{FAVORITES_URL}{listing.id}/", content_type="application/json", **_make_jwt(tenant))
        second = api_client.put(f"{FAVORITES_URL}{listing.id}/", content_type="application/json", **_make_jwt(tenant))

        assert first.status_code == 200
        assert second.status_code == 200
        assert FavoriteListing.objects.filter(user=tenant, listing=listing).count() == 1
        assert first.json()["data"]["id"] == listing.id
        assert first.json()["data"]["is_favorite"] is True
        assert second.json()["data"]["is_favorite"] is True

    def test_put_restores_soft_deleted_favorite(self, api_client):
        tenant = TenantFactory()
        listing = _visible_listing()
        favorite = FavoriteListingFactory(user=tenant, listing=listing)
        favorite.delete()

        response = api_client.put(f"{FAVORITES_URL}{listing.id}/", content_type="application/json", **_make_jwt(tenant))

        assert response.status_code == 200
        assert FavoriteListing.objects.filter(user=tenant, listing=listing).count() == 1
        restored = FavoriteListing.objects.get(user=tenant, listing=listing)
        assert restored.deleted_at is None

    def test_put_rejects_unavailable_listing(self, api_client):
        tenant = TenantFactory()
        hidden_listing = _visible_listing()
        hidden_listing.status = ListingStatus.DRAFT
        hidden_listing.save(update_fields=["status", "updated_at"])

        response = api_client.put(
            f"{FAVORITES_URL}{hidden_listing.id}/",
            content_type="application/json",
            **_make_jwt(tenant),
        )

        assert response.status_code == 404
        assert response.json()["error"] == "listing_unavailable"

    def test_delete_is_idempotent(self, api_client):
        tenant = TenantFactory()
        listing = _visible_listing()
        FavoriteListingFactory(user=tenant, listing=listing)

        first = api_client.delete(f"{FAVORITES_URL}{listing.id}/", **_make_jwt(tenant))
        second = api_client.delete(f"{FAVORITES_URL}{listing.id}/", **_make_jwt(tenant))

        assert first.status_code == 200
        assert second.status_code == 200
        assert FavoriteListing.objects.filter(user=tenant, listing=listing).count() == 0
        assert first.json()["data"] == {"id": listing.id, "is_favorite": False}
        assert second.json()["data"] == {"id": listing.id, "is_favorite": False}

    def test_delete_only_removes_the_authenticated_users_favorite(self, api_client):
        listing = _visible_listing()
        tenant = TenantFactory()
        other_tenant = TenantFactory()
        FavoriteListingFactory(user=tenant, listing=listing)
        FavoriteListingFactory(user=other_tenant, listing=listing)

        response = api_client.delete(f"{FAVORITES_URL}{listing.id}/", **_make_jwt(tenant))

        assert response.status_code == 200
        assert FavoriteListing.objects.filter(user=tenant, listing=listing).count() == 0
        assert FavoriteListing.objects.filter(user=other_tenant, listing=listing).count() == 1
