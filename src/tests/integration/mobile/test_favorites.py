from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.conf import settings
from django.db import close_old_connections, connection
from django.utils import timezone
from marketplace.models import FavoriteListing
from marketplace.services.favorites import FavoriteListingService

from core.constants import ListingStatus, PropertyEngagementType, PropertyStatus
from tests.factories import (
    DistrictFactory,
    FavoriteListingFactory,
    ListingFactory,
    OwnerAgreementFactory,
    PropertyFactory,
    TenantFactory,
)

pytestmark = pytest.mark.django_db

FAVORITES_URL = "/api/v1/mobile/favorites/"
MAP_URL = "/api/v1/mobile/home/listings/map/"


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
        assert response.json() == {
            "success": False,
            "message": "Not authenticated",
            "error": "Not authenticated",
        }

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

        rented_listing = ListingFactory(
            property=PropertyFactory(status=PropertyStatus.RENTED), status=ListingStatus.PUBLISHED
        )
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
        assert (
            FavoriteListing.objects.filter(
                pk__in=[
                    draft_favorite.pk,
                    rented_favorite.pk,
                    managed_without_agreement_favorite.pk,
                    eligible_future_favorite.pk,
                ]
            ).count()
            == 4
        )
        assert FavoriteListing.global_objects.filter(pk=soft_deleted_favorite.pk).exists()


class TestMobileFavoritesListFilters:
    @staticmethod
    def _favorite_with_price(tenant, price):
        # The auto-created listing gets monthly_price=ask_price, and every price
        # filter/sort prefers monthly_price over listed_price.
        listing = _visible_listing()
        listing.monthly_price = price
        listing.save(update_fields=["monthly_price", "updated_at"])
        return FavoriteListingFactory(user=tenant, listing=listing)

    @staticmethod
    def _returned_ids(response):
        return {item["id"] for item in response.json()["data"]["page"]["object_list"]}

    @staticmethod
    def _ordered_ids(response):
        return [item["id"] for item in response.json()["data"]["page"]["object_list"]]

    def test_search_matches_name_address_and_district(self, api_client):
        tenant = TenantFactory()
        district = DistrictFactory(name="Yunusabad")
        by_name = FavoriteListingFactory(user=tenant, listing=_visible_listing(name="Fancy Loft"))
        by_address = FavoriteListingFactory(
            user=tenant, listing=_visible_listing(name="Plain House", address="12 Amir Temur Street")
        )
        by_district = FavoriteListingFactory(
            user=tenant, listing=_visible_listing(name="Plain Flat", address="9 Navoi Street", district=district)
        )
        FavoriteListingFactory(
            user=tenant,
            listing=_visible_listing(
                name="Basic Flat", address="5 Somewhere Road", district=DistrictFactory(name="Chilonzor")
            ),
        )

        for query, expected in (
            ("fancy", {by_name.listing_id}),
            ("amir temur", {by_address.listing_id}),
            ("yunusabad", {by_district.listing_id}),
        ):
            response = api_client.get(FAVORITES_URL, {"q": query}, **_make_jwt(tenant))

            assert response.status_code == 200
            assert self._returned_ids(response) == expected

    def test_price_range_filters_favorites(self, api_client):
        tenant = TenantFactory()
        self._favorite_with_price(tenant, 400)
        matching = self._favorite_with_price(tenant, 600)
        self._favorite_with_price(tenant, 800)

        response = api_client.get(FAVORITES_URL, {"price_min": 500, "price_max": 700}, **_make_jwt(tenant))

        assert response.status_code == 200
        assert self._returned_ids(response) == {matching.listing_id}

    def test_district_and_verified_filters(self, api_client):
        tenant = TenantFactory()
        district = DistrictFactory(name="Filter District")
        verified_in_district = FavoriteListingFactory(
            user=tenant, listing=_visible_listing(district=district, is_verified=True)
        )
        unverified_elsewhere = FavoriteListingFactory(user=tenant, listing=_visible_listing())

        district_response = api_client.get(FAVORITES_URL, {"district_id": district.id}, **_make_jwt(tenant))
        verified_response = api_client.get(FAVORITES_URL, {"verified": "true"}, **_make_jwt(tenant))
        unverified_response = api_client.get(FAVORITES_URL, {"verified": "false"}, **_make_jwt(tenant))

        assert district_response.status_code == 200
        assert self._returned_ids(district_response) == {verified_in_district.listing_id}
        assert verified_response.status_code == 200
        assert self._returned_ids(verified_response) == {verified_in_district.listing_id}
        assert unverified_response.status_code == 200
        assert self._returned_ids(unverified_response) == {unverified_elsewhere.listing_id}

    def test_sort_by_price_ignores_like_recency(self, api_client):
        tenant = TenantFactory()
        # Favorited priciest-first so like-recency order differs from price order.
        expensive = self._favorite_with_price(tenant, 800)
        cheapest = self._favorite_with_price(tenant, 400)
        middle = self._favorite_with_price(tenant, 600)

        ascending = api_client.get(FAVORITES_URL, {"sort": "price_asc"}, **_make_jwt(tenant))
        descending = api_client.get(FAVORITES_URL, {"sort": "price_desc"}, **_make_jwt(tenant))
        recent = api_client.get(FAVORITES_URL, {"sort": "recent"}, **_make_jwt(tenant))

        assert self._ordered_ids(ascending) == [cheapest.listing_id, middle.listing_id, expensive.listing_id]
        assert self._ordered_ids(descending) == [expensive.listing_id, middle.listing_id, cheapest.listing_id]
        assert self._ordered_ids(recent) == [middle.listing_id, cheapest.listing_id, expensive.listing_id]

    def test_filter_combines_with_pagination(self, api_client):
        tenant = TenantFactory()
        self._favorite_with_price(tenant, 100)
        mid = self._favorite_with_price(tenant, 200)
        top = self._favorite_with_price(tenant, 300)
        query = {"price_min": 200, "per_page": 1, "sort": "price_asc"}

        first_page = api_client.get(FAVORITES_URL, {**query, "page": 1}, **_make_jwt(tenant))
        second_page = api_client.get(FAVORITES_URL, {**query, "page": 2}, **_make_jwt(tenant))

        assert first_page.status_code == 200
        data = first_page.json()["data"]
        assert data["count"] == 2
        assert data["num_pages"] == 2
        assert [item["id"] for item in data["page"]["object_list"]] == [mid.listing_id]
        assert [item["id"] for item in second_page.json()["data"]["page"]["object_list"]] == [top.listing_id]

    def test_filter_can_yield_empty_result(self, api_client):
        tenant = TenantFactory()
        self._favorite_with_price(tenant, 400)

        response = api_client.get(FAVORITES_URL, {"price_max": 1}, **_make_jwt(tenant))

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["count"] == 0
        assert data["page"]["object_list"] == []


class TestMobileFavoritesMap:
    BBOX = "69,41,70,42"

    def _map_query(self, **extra):
        return {"bbox": self.BBOX, "favorites_only": "true", **extra}

    def test_favorites_only_requires_authentication(self, api_client):
        response = api_client.get(MAP_URL, self._map_query())

        assert response.status_code == 401
        assert response.json() == {
            "success": False,
            "message": "Not authenticated",
            "error": "Not authenticated",
        }

    def test_favorites_only_returns_only_favorites_inside_bbox(self, api_client):
        tenant = TenantFactory()
        inside_favorite = FavoriteListingFactory(user=tenant, listing=_visible_listing(map_lat=41.31, map_lon=69.28))
        FavoriteListingFactory(user=tenant, listing=_visible_listing(map_lat=40.5, map_lon=68.5))
        _visible_listing(map_lat=41.32, map_lon=69.29)

        response = api_client.get(MAP_URL, self._map_query(), **_make_jwt(tenant))

        assert response.status_code == 200
        data = response.json()["data"]
        assert {item["id"] for item in data["items"]} == {inside_favorite.listing_id}
        assert data["count"] == 1
        assert all(item["is_favorite"] is True for item in data["items"])

    def test_favorites_only_applies_search_filter(self, api_client):
        tenant = TenantFactory()
        match = FavoriteListingFactory(
            user=tenant, listing=_visible_listing(name="Map Loft", map_lat=41.31, map_lon=69.28)
        )
        FavoriteListingFactory(user=tenant, listing=_visible_listing(name="Other Flat", map_lat=41.32, map_lon=69.29))

        response = api_client.get(MAP_URL, self._map_query(q="loft"), **_make_jwt(tenant))

        assert response.status_code == 200
        data = response.json()["data"]
        assert {item["id"] for item in data["items"]} == {match.listing_id}

    def test_map_without_favorites_only_keeps_public_behaviour(self, api_client):
        tenant = TenantFactory()
        FavoriteListingFactory(user=tenant, listing=_visible_listing(map_lat=41.31, map_lon=69.28))
        unfavored = _visible_listing(map_lat=41.32, map_lon=69.29)

        response = api_client.get(MAP_URL, {"bbox": self.BBOX}, **_make_jwt(tenant))

        assert response.status_code == 200
        data = response.json()["data"]
        assert unfavored.id in {item["id"] for item in data["items"]}


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

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.skipif(connection.vendor != "postgresql", reason="requires PostgreSQL conditional uniqueness")
    def test_concurrent_puts_create_one_active_favorite(self, mocker):
        tenant = TenantFactory()
        listing = _visible_listing()
        barrier = Barrier(2)
        original_create = FavoriteListing.objects.create

        def synchronized_create(*args, **kwargs):
            barrier.wait(timeout=10)
            return original_create(*args, **kwargs)

        mocker.patch.object(FavoriteListing.objects, "create", side_effect=synchronized_create)

        def favorite_in_thread():
            close_old_connections()
            try:
                return FavoriteListingService().favorite(tenant, listing).pk
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            favorite_ids = list(executor.map(lambda _: favorite_in_thread(), range(2)))

        assert len(set(favorite_ids)) == 1
        assert FavoriteListing.objects.filter(user=tenant, listing=listing).count() == 1

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.skipif(connection.vendor != "postgresql", reason="requires PostgreSQL row locking")
    def test_concurrent_puts_restore_one_soft_deleted_favorite(self):
        tenant = TenantFactory()
        listing = _visible_listing()
        favorite = FavoriteListingFactory(user=tenant, listing=listing)
        favorite.delete()
        barrier = Barrier(2)

        def favorite_in_thread():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return FavoriteListingService().favorite(tenant, listing).pk
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            favorite_ids = list(executor.map(lambda _: favorite_in_thread(), range(2)))

        assert len(set(favorite_ids)) == 1
        assert FavoriteListing.objects.filter(user=tenant, listing=listing).count() == 1
        assert (
            FavoriteListing.global_objects.filter(user=tenant, listing=listing, deleted_at__isnull=False).count() == 0
        )

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
