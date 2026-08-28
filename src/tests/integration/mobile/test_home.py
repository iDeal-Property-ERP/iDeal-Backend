from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import pytest
from account.models import TokenBlacklist
from django.conf import settings
from django.test import override_settings
from django.urls import resolve
from django.utils import timezone
from marketplace.models import Listing
from property.models import Amenity, Property, PropertyPhoto

from core.constants import (
    FurnishingType,
    LeaseStatus,
    ListingStatus,
    OwnerAgreementStatus,
    PropertyEngagementType,
    PropertyStatus,
    PropertyType,
    TariffChoices,
)
from tests.factories import (
    DistrictFactory,
    LeaseFactory,
    ListingFactory,
    OwnerAgreementFactory,
    PropertyFactory,
    PropertyPhotoFactory,
    TenantFactory,
)

pytestmark = pytest.mark.django_db

LISTINGS_URL = "/api/v1/mobile/home/listings/"
MAP_URL = "/api/v1/mobile/home/listings/map/"
LISTING_DETAIL_URL = "/api/v1/mobile/home/listings/"
FILTERS_URL = "/api/v1/mobile/home/filters/"
RECOMMENDED_URL = "/api/v1/mobile/home/listings/recommended/"


def _make_jwt(user, **overrides):
    from datetime import UTC, datetime, timedelta

    import jwt

    payload = {
        "sub": str(user.id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "jti": overrides.pop("jti", "home-token"),
    }
    payload.update(overrides)
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _make_vacant_listing(**listing_kwargs):
    prop = PropertyFactory(status=PropertyStatus.VACANT)
    listing = prop.listing
    for field, value in listing_kwargs.items():
        setattr(listing, field, value)
    if "status" in listing_kwargs and listing_kwargs["status"] != ListingStatus.PUBLISHED:
        listing.is_active = False
    if listing_kwargs:
        listing.save()
    return listing


def _items(body):
    return body["data"]["page"]["object_list"]


class TestMobileHomeListings:
    def test_anonymous_paginated_card_shape(self, api_client):
        listing = _make_vacant_listing(monthly_price=850, listed_price=900)
        listing.property.score = 4.7
        listing.property.review_count = 12
        listing.property.map_lat = 41.31
        listing.property.map_lon = 69.28
        listing.property.save(update_fields=["score", "review_count", "map_lat", "map_lon", "updated_at"])
        listing.monthly_price = 850
        listing.listed_price = 900
        listing.save(update_fields=["monthly_price", "listed_price", "updated_at"])
        PropertyPhoto.objects.create(
            property=listing.property,
            image="properties/photos/secondary.jpg",
            is_primary=False,
            sort_order=0,
        )
        PropertyPhoto.objects.create(
            property=listing.property,
            image="properties/photos/cover.jpg",
            is_primary=True,
            sort_order=5,
        )
        for i in range(1, 4):
            PropertyPhoto.objects.create(
                property=listing.property,
                image=f"properties/photos/extra_card_{i}.jpg",
                is_primary=False,
                sort_order=i,
            )

        response = api_client.get(LISTINGS_URL)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert {"count", "num_pages", "per_page", "page"} <= data.keys()
        assert data["page"]["number"] == 1
        assert isinstance(data["page"]["object_list"], list)

        card = next(item for item in _items(body) if item["id"] == listing.id)
        assert set(card) == {
            "id",
            "property_id",
            "title",
            "district",
            "address",
            "property_type",
            "rooms",
            "area_sqm",
            "floor",
            "total_floors",
            "furnishing",
            "price",
            "currency",
            "tariff",
            "is_verified",
            "is_featured",
            "score",
            "review_count",
            "cover_image_url",
            "cover_preview_url",
            "cover_display_url",
            "map_lat",
            "map_lon",
            "is_favorite",
        }
        assert card["property_id"] == listing.property_id
        assert card["title"] == listing.property.name
        assert card["price"] == 850.0
        assert isinstance(card["price"], float)
        assert isinstance(card["score"], float)
        assert card["cover_image_url"].startswith(("http://", "https://"))
        assert urlparse(card["cover_image_url"]).path.endswith("cover.jpg")
        assert card["cover_preview_url"] is None
        assert card["cover_display_url"] is None
        assert card["is_favorite"] is False

    def test_invalid_optional_auth_keeps_is_favorite_false(self, api_client, tenant):
        listing = _make_vacant_listing()
        response = api_client.get(LISTINGS_URL, HTTP_AUTHORIZATION="Bearer invalid-token")

        assert response.status_code == 200
        card = next(item for item in _items(response.json()) if item["id"] == listing.id)
        assert card["is_favorite"] is False

    def test_missing_optional_auth_keeps_is_favorite_false(self, api_client):
        listing = _make_vacant_listing()

        response = api_client.get(LISTINGS_URL)

        assert response.status_code == 200
        card = next(item for item in _items(response.json()) if item["id"] == listing.id)
        assert card["is_favorite"] is False

    def test_blacklisted_optional_auth_keeps_is_favorite_false(self, api_client, tenant):
        listing = _make_vacant_listing()
        TokenBlacklist.objects.create(jti="revoked-home-token")

        response = api_client.get(LISTINGS_URL, **_make_jwt(tenant, jti="revoked-home-token"))

        assert response.status_code == 200
        card = next(item for item in _items(response.json()) if item["id"] == listing.id)
        assert card["is_favorite"] is False

    def test_expired_optional_auth_keeps_is_favorite_false(self, api_client, tenant):
        from datetime import UTC, datetime, timedelta

        from tests.factories import FavoriteListingFactory

        listing = _make_vacant_listing()
        FavoriteListingFactory(user=tenant, listing=listing)
        headers = _make_jwt(
            tenant,
            exp=datetime.now(UTC) - timedelta(minutes=1),
            jti="expired-home-token",
        )

        response = api_client.get(LISTINGS_URL, **headers)

        assert response.status_code == 200
        card = next(item for item in _items(response.json()) if item["id"] == listing.id)
        assert card["is_favorite"] is False

    def test_valid_optional_auth_personalizes_is_favorite(self, api_client, tenant):
        from tests.factories import FavoriteListingFactory

        favorite_listing = _make_vacant_listing()
        other_listing = _make_vacant_listing()
        FavoriteListingFactory(user=tenant, listing=favorite_listing)

        response = api_client.get(LISTINGS_URL, **_make_jwt(tenant, jti="valid-home-token"))

        assert response.status_code == 200
        cards = {
            item["id"]: item
            for item in _items(response.json())
            if item["id"] in {favorite_listing.id, other_listing.id}
        }
        assert cards[favorite_listing.id]["is_favorite"] is True
        assert cards[other_listing.id]["is_favorite"] is False

    def test_case_insensitive_bearer_scheme_personalizes_is_favorite(self, api_client, tenant):
        from tests.factories import FavoriteListingFactory

        listing = _make_vacant_listing()
        FavoriteListingFactory(user=tenant, listing=listing)
        token = _make_jwt(tenant, jti="case-insensitive-bearer-token")["HTTP_AUTHORIZATION"].split(" ", 1)[1]

        response = api_client.get(LISTINGS_URL, HTTP_AUTHORIZATION=f"bEaReR {token}")

        assert response.status_code == 200
        card = next(item for item in _items(response.json()) if item["id"] == listing.id)
        assert card["is_favorite"] is True

    @pytest.mark.parametrize("scheme", ["Basic", "Token", "Digest"])
    def test_non_bearer_scheme_does_not_personalize(self, api_client, tenant, scheme):
        from tests.factories import FavoriteListingFactory

        listing = _make_vacant_listing()
        FavoriteListingFactory(user=tenant, listing=listing)
        token = _make_jwt(tenant, jti=f"non-bearer-{scheme}")["HTTP_AUTHORIZATION"].split(" ", 1)[1]

        response = api_client.get(LISTINGS_URL, HTTP_AUTHORIZATION=f"{scheme} {token}")

        assert response.status_code == 200
        card = next(item for item in _items(response.json()) if item["id"] == listing.id)
        assert card["is_favorite"] is False

    @pytest.mark.parametrize("authorization", ["Bearer", "Bearer ", "Bearer token extra", "Basic"])
    def test_malformed_optional_auth_header_keeps_anonymous_fallback(self, api_client, tenant, authorization):
        from tests.factories import FavoriteListingFactory

        listing = _make_vacant_listing()
        FavoriteListingFactory(user=tenant, listing=listing)

        response = api_client.get(LISTINGS_URL, HTTP_AUTHORIZATION=authorization)

        assert response.status_code == 200
        card = next(item for item in _items(response.json()) if item["id"] == listing.id)
        assert card["is_favorite"] is False

    def test_cover_variant_urls_are_absolute_when_present(self, api_client):
        listing = _make_vacant_listing()
        photo = PropertyPhoto.objects.create(
            property=listing.property,
            image="properties/photos/original.jpg",
            is_primary=True,
            sort_order=0,
        )
        for i in range(1, 5):
            PropertyPhoto.objects.create(
                property=listing.property,
                image=f"properties/photos/extra{i}.jpg",
                is_primary=False,
                sort_order=i,
            )
        PropertyPhoto.objects.filter(pk=photo.pk).update(
            preview_image="properties/photos/variants/preview.webp",
            display_image="properties/photos/variants/display.webp",
        )

        response = api_client.get(LISTINGS_URL)

        card = next(item for item in _items(response.json()) if item["id"] == listing.id)
        assert urlparse(card["cover_preview_url"]).path.endswith("variants/preview.webp")
        assert urlparse(card["cover_display_url"]).path.endswith("variants/display.webp")
        assert card["cover_preview_url"].startswith(("http://", "https://"))
        assert card["cover_display_url"].startswith(("http://", "https://"))

    def test_published_and_vacancy_gates(self, api_client):
        visible = _make_vacant_listing()
        pending = _make_vacant_listing(status=ListingStatus.PENDING_REVIEW)
        archived = _make_vacant_listing(status=ListingStatus.ARCHIVED)
        rented_property = PropertyFactory(status=PropertyStatus.RENTED)
        rented = ListingFactory(property=rented_property, status=ListingStatus.PUBLISHED)

        response = api_client.get(LISTINGS_URL)

        assert response.status_code == 200
        ids = {item["id"] for item in _items(response.json())}
        assert visible.id in ids
        assert pending.id not in ids
        assert archived.id not in ids
        assert rented.id not in ids

    def test_nullable_property_specs_are_serialized_as_null(self, api_client):
        """rooms/area_sqm/floor/total_floors are nullable on Property; real rows do have
        NULLs there, so the card schema must not require them."""
        listing = _make_vacant_listing()
        listing.property.rooms = None
        listing.property.area_sqm = None
        listing.property.floor = None
        listing.property.total_floors = None
        listing.property.save(update_fields=["rooms", "area_sqm", "floor", "total_floors", "updated_at"])

        response = api_client.get(LISTINGS_URL)

        assert response.status_code == 200
        item = next(i for i in _items(response.json()) if i["id"] == listing.id)
        assert item["rooms"] is None
        assert item["area_sqm"] is None
        assert item["floor"] is None
        assert item["total_floors"] is None

    def test_core_filters_narrow_results(self, api_client):
        matching_district = DistrictFactory(name="Mobile Filter District")
        other_district = DistrictFactory(name="Mobile Other District")
        matching_property = PropertyFactory(
            name="Sunny Mobile Apartment",
            district=matching_district,
            property_type=PropertyType.HOUSE,
            rooms=3,
            furnishing=FurnishingType.FURNISHED,
            tariff=TariffChoices.PREMIUM,
            is_verified=True,
            status=PropertyStatus.VACANT,
        )
        matching = matching_property.listing
        matching.monthly_price = 1200
        matching.listed_price = 1200
        matching.save()

        other_property = PropertyFactory(
            name="Other Mobile Home",
            district=other_district,
            property_type=PropertyType.APARTMENT,
            rooms=1,
            furnishing=FurnishingType.UNFURNISHED,
            tariff=TariffChoices.STANDARD,
            is_verified=False,
            status=PropertyStatus.VACANT,
        )
        other = other_property.listing
        other.monthly_price = 400
        other.listed_price = 400
        other.save()
        high_property = PropertyFactory(
            name="High Price Mobile Home",
            district=other_district,
            property_type=PropertyType.STUDIO,
            rooms=5,
            furnishing=FurnishingType.UNFURNISHED,
            tariff=TariffChoices.STANDARD,
            is_verified=False,
            status=PropertyStatus.VACANT,
        )
        high = high_property.listing
        high.monthly_price = 1800
        high.listed_price = 1800
        high.save()

        filter_queries = [
            ({"q": "Sunny"}, {matching.id}),
            ({"district_id": matching_district.id}, {matching.id}),
            ({"price_min": 1000}, {matching.id, high.id}),
            ({"price_max": 1500}, {matching.id, other.id}),
            ({"rooms_min": 3}, {matching.id, high.id}),
            ({"rooms_max": 3}, {matching.id, other.id}),
            ({"verified": "true"}, {matching.id}),
            ({"furnishing": FurnishingType.FURNISHED}, {matching.id}),
            ({"tariff": TariffChoices.PREMIUM}, {matching.id}),
            ({"property_type": PropertyType.HOUSE}, {matching.id}),
        ]
        for query, expected_ids in filter_queries:
            response = api_client.get(LISTINGS_URL, query)
            assert response.status_code == 200, query
            assert {item["id"] for item in _items(response.json())} == expected_ids, query

    def test_pagination_returns_next_slice(self, api_client):
        listings = [_make_vacant_listing() for _ in range(5)]
        all_response = api_client.get(LISTINGS_URL, {"per_page": 20})
        expected_ids = [item["id"] for item in _items(all_response.json()) if item["id"] in {x.id for x in listings}]

        page_one = api_client.get(LISTINGS_URL, {"page": 1, "per_page": 2}).json()
        page_two = api_client.get(LISTINGS_URL, {"page": 2, "per_page": 2}).json()

        assert page_one["data"]["num_pages"] == 3
        assert [item["id"] for item in _items(page_one)] == expected_ids[:2]
        assert [item["id"] for item in _items(page_two)] == expected_ids[2:4]

    def test_score_sorting_is_supported(self, api_client):
        low = _make_vacant_listing()
        mid = _make_vacant_listing()
        high = _make_vacant_listing()

        low.property.score = 2.4
        low.property.save(update_fields=["score", "updated_at"])
        mid.property.score = 6.9
        mid.property.save(update_fields=["score", "updated_at"])
        high.property.score = 9.8
        high.property.save(update_fields=["score", "updated_at"])

        response = api_client.get(LISTINGS_URL, {"sort": "score_desc"})
        assert response.status_code == 200
        items = _items(response.json())
        test_ids = [item["id"] for item in items if item["id"] in {low.id, mid.id, high.id}]
        assert test_ids == [high.id, mid.id, low.id]


class TestMobileHomeListingMap:
    BBOX = "69,41,70,42"

    @staticmethod
    def _set_coordinates(listing, *, lat: float | None = 41.31, lon: float | None = 69.28):
        Property.objects.filter(pk=listing.property_id).update(map_lat=lat, map_lon=lon)
        listing.property.refresh_from_db()

    def test_route_is_registered_before_dynamic_listing_detail(self):
        match = resolve(MAP_URL)

        assert match.url_name == "listing-map"

    @pytest.mark.parametrize(
        "bbox",
        [
            None,
            "",
            "69,41,70",
            "69,41,70,42,43",
            "west,41,70,42",
            "nan,41,70,42",
            "69,41,inf,42",
            "-181,41,70,42",
            "69,-91,70,42",
            "69,41,181,42",
            "69,41,70,91",
            "70,41,69,42",
            "69,42,70,41",
            "69,41,69,42",
            "69,41,70,41",
        ],
    )
    def test_bbox_is_required_and_strictly_validated(self, api_client, bbox):
        query = {} if bbox is None else {"bbox": bbox}

        response = api_client.get(MAP_URL, query)

        assert response.status_code == 400

    def test_bbox_filters_coordinates_and_excludes_nulls(self, api_client):
        inside = _make_vacant_listing()
        self._set_coordinates(inside)
        outside = _make_vacant_listing()
        self._set_coordinates(outside, lat=40.5, lon=68.5)
        null_lat = _make_vacant_listing()
        self._set_coordinates(null_lat, lat=None, lon=69.3)
        null_lon = _make_vacant_listing()
        self._set_coordinates(null_lon, lat=41.3, lon=None)

        response = api_client.get(MAP_URL, {"bbox": self.BBOX})

        assert response.status_code == 200
        data = response.json()["data"]
        assert {item["id"] for item in data["items"]} == {inside.id}
        assert data["count"] == 1
        assert data["truncated"] is False

    def test_supported_filters_match_mobile_feed(self, api_client):
        matching_district = DistrictFactory(name="Map Filter District")
        other_district = DistrictFactory(name="Map Other District")
        matching_property = PropertyFactory(
            name="Sunny Map House",
            district=matching_district,
            property_type=PropertyType.HOUSE,
            rooms=3,
            furnishing=FurnishingType.FURNISHED,
            tariff=TariffChoices.PREMIUM,
            is_verified=True,
            status=PropertyStatus.VACANT,
            map_lat=41.31,
            map_lon=69.28,
        )
        matching = matching_property.listing
        matching.monthly_price = 1200
        matching.listed_price = 1200
        matching.save(update_fields=["monthly_price", "listed_price", "updated_at"])
        other_property = PropertyFactory(
            name="Other Map Apartment",
            district=other_district,
            property_type=PropertyType.APARTMENT,
            rooms=1,
            furnishing=FurnishingType.UNFURNISHED,
            tariff=TariffChoices.STANDARD,
            is_verified=False,
            status=PropertyStatus.VACANT,
            map_lat=41.32,
            map_lon=69.29,
        )
        other = other_property.listing
        other.monthly_price = 400
        other.listed_price = 400
        other.save(update_fields=["monthly_price", "listed_price", "updated_at"])
        high_property = PropertyFactory(
            name="High Price Map Studio",
            district=other_district,
            property_type=PropertyType.STUDIO,
            rooms=5,
            furnishing=FurnishingType.UNFURNISHED,
            tariff=TariffChoices.STANDARD,
            is_verified=False,
            status=PropertyStatus.VACANT,
            map_lat=41.33,
            map_lon=69.30,
        )
        high = high_property.listing
        high.monthly_price = 1800
        high.listed_price = 1800
        high.save(update_fields=["monthly_price", "listed_price", "updated_at"])

        filter_queries = [
            ({"q": "Sunny"}, {matching.id}),
            ({"district_id": matching_district.id}, {matching.id}),
            ({"property_type": PropertyType.HOUSE}, {matching.id}),
            ({"price_min": 1000}, {matching.id, high.id}),
            ({"price_max": 1500}, {matching.id, other.id}),
            ({"rooms_min": 3}, {matching.id, high.id}),
            ({"rooms_max": 3}, {matching.id, other.id}),
            ({"verified": "true"}, {matching.id}),
            ({"furnishing": FurnishingType.FURNISHED}, {matching.id}),
            ({"tariff": TariffChoices.PREMIUM}, {matching.id}),
        ]
        for query, expected_ids in filter_queries:
            map_response = api_client.get(MAP_URL, {"bbox": self.BBOX, **query})
            feed_response = api_client.get(LISTINGS_URL, query)

            assert map_response.status_code == 200, query
            assert feed_response.status_code == 200, query
            map_ids = {item["id"] for item in map_response.json()["data"]["items"]}
            feed_ids = {item["id"] for item in _items(feed_response.json())}
            assert map_ids == expected_ids, query
            assert map_ids == feed_ids, query

    def test_eligibility_matches_feed_including_future_managed(self, api_client, mocker):
        mocker.patch("marketplace.services.booking.BookingService.enabled_providers", return_value=["click"])
        visible = _make_vacant_listing()
        self._set_coordinates(visible)
        pending = _make_vacant_listing(status=ListingStatus.PENDING_REVIEW)
        self._set_coordinates(pending)
        archived = _make_vacant_listing(status=ListingStatus.ARCHIVED)
        self._set_coordinates(archived)
        rented_without_agreement_property = PropertyFactory(
            status=PropertyStatus.RENTED,
            engagement_type=PropertyEngagementType.MANAGED,
            is_verified=True,
            map_lat=41.34,
            map_lon=69.31,
        )
        rented_without_agreement = ListingFactory(
            property=rented_without_agreement_property,
            status=ListingStatus.PUBLISHED,
        )
        future_property = PropertyFactory(
            status=PropertyStatus.RENTED,
            engagement_type=PropertyEngagementType.MANAGED,
            is_verified=True,
            map_lat=41.35,
            map_lon=69.32,
        )
        future_managed = ListingFactory(property=future_property, status=ListingStatus.PUBLISHED)
        OwnerAgreementFactory(
            property=future_property,
            owner=future_property.owner,
            start_date=timezone.localdate() - timedelta(days=30),
            end_date=timezone.localdate() + timedelta(days=30),
        )

        map_response = api_client.get(MAP_URL, {"bbox": self.BBOX})
        feed_response = api_client.get(LISTINGS_URL)

        assert map_response.status_code == 200
        map_ids = {item["id"] for item in map_response.json()["data"]["items"]}
        feed_ids = {item["id"] for item in _items(feed_response.json())}
        assert map_ids == {visible.id, future_managed.id}
        assert map_ids == feed_ids
        assert pending.id not in map_ids
        assert archived.id not in map_ids
        assert rented_without_agreement.id not in map_ids

    def test_item_reuses_card_shape_with_non_null_coordinates_and_contact(self, api_client):
        listing = _make_vacant_listing(monthly_price=850, listed_price=900)
        self._set_coordinates(listing)
        photo = PropertyPhoto.objects.create(
            property=listing.property,
            image="properties/photos/map-original.jpg",
            is_primary=True,
            sort_order=0,
        )
        for i in range(1, 5):
            PropertyPhoto.objects.create(
                property=listing.property,
                image=f"properties/photos/map-extra{i}.jpg",
                is_primary=False,
                sort_order=i,
            )
        PropertyPhoto.objects.filter(pk=photo.pk).update(
            preview_image="properties/photos/variants/map-preview.webp",
            display_image="properties/photos/variants/map-display.webp",
        )

        with override_settings(PLATFORM_CONTACT_PHONE="+998 71 200 00 00"):
            response = api_client.get(MAP_URL, {"bbox": self.BBOX})

        assert response.status_code == 200
        data = response.json()["data"]
        assert set(data) == {"items", "count", "truncated"}
        item = data["items"][0]
        assert set(item) == {
            "id",
            "property_id",
            "title",
            "district",
            "address",
            "property_type",
            "rooms",
            "area_sqm",
            "floor",
            "total_floors",
            "furnishing",
            "price",
            "currency",
            "tariff",
            "is_verified",
            "is_featured",
            "score",
            "review_count",
            "cover_image_url",
            "cover_preview_url",
            "cover_display_url",
            "map_lat",
            "map_lon",
            "contact_phone",
            "is_favorite",
        }
        assert item["map_lat"] == 41.31
        assert item["map_lon"] == 69.28
        assert item["contact_phone"] == "+998 71 200 00 00"
        assert item["is_favorite"] is False
        assert urlparse(item["cover_image_url"]).path.endswith("map-original.jpg")
        assert urlparse(item["cover_preview_url"]).path.endswith("map-preview.webp")
        assert urlparse(item["cover_display_url"]).path.endswith("map-display.webp")

    def test_empty_platform_contact_is_null(self, api_client):
        listing = _make_vacant_listing()
        self._set_coordinates(listing)

        with override_settings(PLATFORM_CONTACT_PHONE=""):
            response = api_client.get(MAP_URL, {"bbox": self.BBOX})

        assert response.status_code == 200
        assert response.json()["data"]["items"][0]["contact_phone"] is None

    def test_response_is_deterministically_capped_at_500(self, api_client):
        properties = Property.objects.bulk_create(
            [
                Property(
                    name=f"Map listing {index}",
                    status=PropertyStatus.VACANT,
                    map_lat=41.31,
                    map_lon=69.28,
                )
                for index in range(501)
            ]
        )
        Listing.objects.bulk_create(
            [
                Listing(
                    property=prop,
                    status=ListingStatus.PUBLISHED,
                    listed_price=500,
                    monthly_price=500,
                )
                for prop in properties
            ]
        )

        first_response = api_client.get(MAP_URL, {"bbox": self.BBOX})
        second_response = api_client.get(MAP_URL, {"bbox": self.BBOX})

        assert first_response.status_code == 200
        first = first_response.json()["data"]
        second = second_response.json()["data"]
        assert first["count"] == 501
        assert len(first["items"]) == 500
        assert first["truncated"] is True
        assert [item["id"] for item in first["items"]] == [item["id"] for item in second["items"]]


class TestMobileHomeListingDetail:
    def test_anonymous_detail_shape_and_numeric_types(self, api_client):
        listing = _make_vacant_listing()
        listing.property.score = 4.7
        listing.property.deposit_amount = 300
        listing.property.description = "A bright home near the city center."
        listing.property.save()
        # Saving the property re-fires manage_listing_on_property_change, which mirrors
        # ask_price/description onto the listing — so set the listing's own values after it.
        listing.refresh_from_db()
        listing.monthly_price = 850
        listing.listed_price = 900
        listing.description = None
        listing.description_en = None
        listing.description_uz = None
        listing.description_ru = None
        listing.deposit_amount = None
        listing.price_includes = ["utilities"]
        listing.save()

        response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert set(data) == {
            "id",
            "property_id",
            "title",
            "district",
            "address",
            "property_type",
            "rooms",
            "area_sqm",
            "floor",
            "total_floors",
            "furnishing",
            "price",
            "currency",
            "tariff",
            "is_verified",
            "is_featured",
            "score",
            "review_count",
            "map_lat",
            "map_lon",
            "description",
            "deposit_amount",
            "minimum_stay",
            "price_includes",
            "created_at",
            "photos",
            "amenities",
            "verification",
            "can_message",
            "contact_phone",
            "booking",
        }
        assert data["price"] == 850.0
        assert isinstance(data["price"], float)
        assert isinstance(data["score"], float)
        assert isinstance(data["deposit_amount"], (float, type(None)))
        assert data["deposit_amount"] == 300.0
        assert data["description"] == listing.property.description
        assert data["can_message"] is True
        assert data["booking"]["eligible"] is False

    def test_detail_photos_are_primary_first_and_have_absolute_urls(self, api_client):
        listing = _make_vacant_listing()
        late = PropertyPhotoFactory(
            property=listing.property,
            image="properties/photos/late.jpg",
            caption="Late photo",
            sort_order=20,
        )
        primary = PropertyPhotoFactory(
            property=listing.property,
            image="properties/photos/primary.jpg",
            is_primary=True,
            sort_order=99,
        )
        early = PropertyPhotoFactory(
            property=listing.property,
            image="properties/photos/early.jpg",
            sort_order=1,
        )
        extra1 = PropertyPhotoFactory(
            property=listing.property,
            image="properties/photos/extra1.jpg",
            sort_order=100,
        )
        extra2 = PropertyPhotoFactory(
            property=listing.property,
            image="properties/photos/extra2.jpg",
            sort_order=101,
        )

        response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")

        assert response.status_code == 200
        photos = response.json()["data"]["photos"]
        assert [photo["id"] for photo in photos] == [primary.id, early.id, late.id, extra1.id, extra2.id]
        assert all(
            set(photo) == {"id", "image_url", "preview_url", "display_url", "caption", "is_primary", "sort_order"}
            for photo in photos
        )
        assert all(photo["image_url"].startswith(("http://", "https://")) for photo in photos)
        assert all(photo["preview_url"] is None and photo["display_url"] is None for photo in photos)
        assert photos[0]["caption"] is None
        assert urlparse(photos[0]["image_url"]).path.endswith("primary.jpg")

    def test_detail_amenities_exclude_inactive_entries(self, api_client):
        listing = _make_vacant_listing()
        active_late = Amenity.objects.create(slug="mobile-active-late", name="Zeta", sort_order=20)
        inactive = Amenity.objects.create(slug="mobile-inactive", name="Hidden", sort_order=0, is_active=False)
        active_early = Amenity.objects.create(slug="mobile-active-early", name="Alpha", sort_order=10)
        listing.property.amenities.set([active_late, inactive, active_early])

        response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")

        assert response.status_code == 200
        amenities = response.json()["data"]["amenities"]
        assert [amenity["slug"] for amenity in amenities] == [active_early.slug, active_late.slug]
        assert inactive.slug not in {amenity["slug"] for amenity in amenities}

    def test_detail_verification_checklist_has_key_and_label(self, api_client):
        listing = _make_vacant_listing()
        listing.property.is_verified = True
        listing.property.save(update_fields=["is_verified"])

        response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")

        assert response.status_code == 200
        checklist = response.json()["data"]["verification"]["checklist"]
        assert checklist
        assert all(set(item) == {"key", "label"} for item in checklist)
        assert all(item["key"] and item["label"] for item in checklist)

    def test_detail_hides_verification_checklist_when_unverified(self, api_client):
        listing = _make_vacant_listing()

        response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")

        assert response.status_code == 200
        verification = response.json()["data"]["verification"]
        assert verification == {"is_verified": False, "checklist": []}

    def test_detail_marks_unpublished_listing_as_not_messageable(self, api_client):
        listing = _make_vacant_listing(status=ListingStatus.PENDING_REVIEW)

        response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")

        assert response.status_code == 200
        assert response.json()["data"]["can_message"] is False

    def test_detail_marks_soft_deleted_listing_as_not_messageable(self, api_client):
        listing = _make_vacant_listing()
        listing.delete()

        response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")

        assert response.status_code == 200
        assert response.json()["data"]["can_message"] is False

    def test_detail_returns_404_for_unknown_listing(self, api_client):
        response = api_client.get(f"{LISTING_DETAIL_URL}999999999/")

        assert response.status_code == 404

    def test_detail_allows_published_listing_when_property_is_rented(self, api_client):
        prop = PropertyFactory(status=PropertyStatus.RENTED)
        listing = ListingFactory(property=prop, status=ListingStatus.PUBLISHED)

        response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")

        assert response.status_code == 200

    def test_detail_allows_message_for_one_off_listing_without_owner(self, api_client):
        prop = PropertyFactory(engagement_type=PropertyEngagementType.ONE_OFF, owner=None)
        listing = ListingFactory(property=prop, status=ListingStatus.PUBLISHED)

        response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")

        assert response.status_code == 200
        assert response.json()["data"]["can_message"] is True

    def test_detail_contact_phone_follows_platform_setting(self, api_client):
        listing = _make_vacant_listing()

        with override_settings(PLATFORM_CONTACT_PHONE=""):
            empty_response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")
        with override_settings(PLATFORM_CONTACT_PHONE="+998 71 200 00 00"):
            configured_response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")

        assert empty_response.status_code == 200
        assert empty_response.json()["data"]["contact_phone"] is None
        assert configured_response.status_code == 200
        assert configured_response.json()["data"]["contact_phone"] == "+998 71 200 00 00"


class TestMobileHomeFilters:
    def test_filters_are_public_and_include_localized_options(self, api_client):
        DistrictFactory(name="Filters District")
        low = _make_vacant_listing(monthly_price=200, listed_price=200)
        high = _make_vacant_listing(monthly_price=2000, listed_price=2000)
        low.property.rooms = 1
        low.property.save(update_fields=["rooms", "updated_at"])
        high.property.rooms = 5
        high.property.save(update_fields=["rooms", "updated_at"])
        low.monthly_price = 200
        low.listed_price = 200
        low.save(update_fields=["monthly_price", "listed_price", "updated_at"])
        high.monthly_price = 2000
        high.listed_price = 2000
        high.save(update_fields=["monthly_price", "listed_price", "updated_at"])

        response = api_client.get(FILTERS_URL)

        assert response.status_code == 200
        data = response.json()["data"]
        assert set(data) == {"districts", "tariffs", "furnishings", "property_types", "price", "rooms"}
        assert any(district["name"] == "Filters District" for district in data["districts"])
        assert data["tariffs"] == [{"value": value, "label": str(label)} for value, label in TariffChoices.CHOICES]
        assert data["furnishings"] == [{"value": value, "label": str(label)} for value, label in FurnishingType.CHOICES]
        assert data["property_types"] == [
            {"value": value, "label": str(label)} for value, label in PropertyType.CHOICES
        ]
        assert data["price"] == {"min": 200.0, "max": 2000.0}
        assert data["rooms"] == {"min": 1, "max": 5}

    def test_empty_published_queryset_returns_null_bounds(self, api_client):
        Listing.objects.all().delete()

        response = api_client.get(FILTERS_URL)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["price"] == {"min": None, "max": None}
        assert data["rooms"] == {"min": None, "max": None}


class TestMobileHomeRecommendedListings:
    @pytest.mark.parametrize("method", ["get", "post"])
    def test_recommended_requires_authentication(self, api_client, method):
        if method == "get":
            response = api_client.get(RECOMMENDED_URL)
        else:
            response = api_client.post(
                RECOMMENDED_URL,
                data={"type": "view", "listing_id": 1},
                content_type="application/json",
            )

        assert response.status_code == 401
        assert response.json()["success"] is False

    def test_recommended_route_ordering_not_shadowed_by_detail(self):
        match = resolve(RECOMMENDED_URL)
        assert match.url_name == "listings-recommended"

    def test_recommended_get_empty_when_no_activity(self, api_client):
        user = TenantFactory()
        headers = _make_jwt(user)

        response = api_client.get(RECOMMENDED_URL, **headers)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == {"items": [], "count": 0}

    def test_record_search_and_deduplication(self, api_client):
        from marketplace.models import RecentSearchActivity

        user = TenantFactory()
        headers = _make_jwt(user)

        payload = {"type": "search", "query": "Yunusabad", "filters": {"rooms_min": 2, "price_max": 1000}}
        response1 = api_client.post(RECOMMENDED_URL, data=payload, content_type="application/json", **headers)

        assert response1.status_code == 200
        assert response1.json()["data"]["recorded"] is True
        assert RecentSearchActivity.objects.filter(user=user).count() == 1

        first_activity = RecentSearchActivity.objects.get(user=user)
        assert first_activity.query == "Yunusabad"
        assert first_activity.filters["rooms_min"] == 2
        first_updated_at = first_activity.updated_at

        # Repeat same search
        response2 = api_client.post(RECOMMENDED_URL, data=payload, content_type="application/json", **headers)
        assert response2.status_code == 200
        assert RecentSearchActivity.objects.filter(user=user).count() == 1

        first_activity.refresh_from_db()
        assert first_activity.updated_at >= first_updated_at

    def test_record_search_validation_error_on_empty_criteria(self, api_client):
        user = TenantFactory()
        headers = _make_jwt(user)

        payload = {"type": "search", "query": "   ", "filters": {}}
        response = api_client.post(RECOMMENDED_URL, data=payload, content_type="application/json", **headers)

        assert response.status_code == 400
        assert response.json()["success"] is False

    def test_record_search_pruning_at_20(self, api_client):
        from marketplace.models import RecentSearchActivity

        user = TenantFactory()
        headers = _make_jwt(user)

        for i in range(25):
            payload = {"type": "search", "query": f"search-{i}"}
            api_client.post(RECOMMENDED_URL, data=payload, content_type="application/json", **headers)

        assert RecentSearchActivity.objects.filter(user=user).count() == 20
        # The 5 oldest searches should have been pruned
        queries = list(
            RecentSearchActivity.objects.filter(user=user)
            .order_by("-updated_at", "-id")
            .values_list("query", flat=True)
        )
        assert "search-24" in queries
        assert "search-0" not in queries

    def test_record_view_and_deduplication(self, api_client):
        from marketplace.models import ListingViewActivity

        user = TenantFactory()
        headers = _make_jwt(user)
        listing = _make_vacant_listing()

        payload = {"type": "view", "listing_id": listing.id}
        response1 = api_client.post(RECOMMENDED_URL, data=payload, content_type="application/json", **headers)

        assert response1.status_code == 200
        assert response1.json()["data"]["recorded"] is True
        assert ListingViewActivity.objects.filter(user=user).count() == 1

        first_activity = ListingViewActivity.objects.get(user=user)
        first_updated_at = first_activity.updated_at

        # Repeat view
        response2 = api_client.post(RECOMMENDED_URL, data=payload, content_type="application/json", **headers)
        assert response2.status_code == 200
        assert ListingViewActivity.objects.filter(user=user).count() == 1

        first_activity.refresh_from_db()
        assert first_activity.updated_at >= first_updated_at

    def test_record_view_404_for_unknown_listing(self, api_client):
        user = TenantFactory()
        headers = _make_jwt(user)

        payload = {"type": "view", "listing_id": 9999999}
        response = api_client.post(RECOMMENDED_URL, data=payload, content_type="application/json", **headers)

        assert response.status_code == 404
        assert response.json()["success"] is False

    def test_record_view_pruning_at_100(self, api_client):
        from marketplace.models import ListingViewActivity

        user = TenantFactory()
        headers = _make_jwt(user)
        listings = [_make_vacant_listing() for _ in range(105)]

        for listing in listings:
            payload = {"type": "view", "listing_id": listing.id}
            api_client.post(RECOMMENDED_URL, data=payload, content_type="application/json", **headers)

        assert ListingViewActivity.objects.filter(user=user).count() == 100

    def test_recommended_scoring_and_exclusions(self, api_client):
        from marketplace.services.recommendations import RecommendationService

        district_a = DistrictFactory(name="District A")
        district_b = DistrictFactory(name="District B")

        # Candidate 1: matches search query + district A
        l1 = _make_vacant_listing(monthly_price=500)
        l1.property.name = "Luxury Villa"
        l1.property.district = district_a
        l1.property.save(update_fields=["name", "district"])

        # Candidate 2: matches district A only
        l2 = _make_vacant_listing(monthly_price=500)
        l2.property.name = "Simple Cottage"
        l2.property.district = district_a
        l2.property.save(update_fields=["name", "district"])

        # Candidate 3 is intentionally unrelated to every view-seed scoring
        # dimension: district, type, rooms, price, tokens, area, furnishing,
        # and tariff.  This protects the documented any-seed algorithm rather
        # than accidentally relying on factory defaults.
        l3 = _make_vacant_listing(monthly_price=1500)
        l3.property.name = "Remote Estate"
        l3.property.address = "999 Completely Elsewhere Road"
        l3.property.district = district_b
        l3.property.property_type = "house"
        l3.property.rooms = 5
        l3.property.area_sqm = 1000
        l3.property.furnishing = "unfurnished"
        l3.property.tariff = "premium"
        l3.property.save(
            update_fields=[
                "name",
                "address",
                "district",
                "property_type",
                "rooms",
                "area_sqm",
                "furnishing",
                "tariff",
            ]
        )
        # Property saves synchronize listing prices. Reapply this intentional
        # out-of-range candidate price after the property mutation.
        Listing.objects.filter(pk=l3.pk).update(monthly_price=1500, listed_price=1500)
        l3.refresh_from_db()

        # Viewed listing (should be excluded from recommendations)
        viewed_listing = _make_vacant_listing(monthly_price=500)
        viewed_listing.property.district = district_a
        viewed_listing.property.property_type = "apartment"
        viewed_listing.property.rooms = 2
        viewed_listing.property.area_sqm = 100
        viewed_listing.property.furnishing = "furnished"
        viewed_listing.property.tariff = "standard"
        viewed_listing.property.address = "100 Seed Avenue"
        viewed_listing.property.save(
            update_fields=["district", "property_type", "rooms", "area_sqm", "furnishing", "tariff", "address"]
        )

        user = TenantFactory()
        headers = _make_jwt(user)

        # Record search matching "Luxury" and district A
        recommendations = RecommendationService()
        recommendations.record_search(user, "Luxury", {"district_id": district_a.id})
        # Record view on viewed_listing
        recommendations.record_view(user, viewed_listing.id)

        response = api_client.get(RECOMMENDED_URL, **headers)

        assert response.status_code == 200
        items = response.json()["data"]["items"]
        item_ids = [item["id"] for item in items]

        # l1 (Villa) matches both query (+5) and district (+5), scores highest
        # l2 (Cottage) matches district (+5)
        # viewed_listing is excluded
        # l3 (Far away) score is 0, so excluded
        assert l1.id in item_ids
        assert l2.id in item_ids
        assert viewed_listing.id not in item_ids
        assert l3.id not in item_ids
        assert item_ids.index(l1.id) < item_ids.index(l2.id)

    def test_account_deletion_hard_deletes_activity_history(self):
        from account.services.deletion import AccountDeletionService
        from marketplace.models import ListingViewActivity, RecentSearchActivity
        from marketplace.services.recommendations import RecommendationService

        user = TenantFactory()
        listing = _make_vacant_listing()

        recommendations = RecommendationService()
        recommendations.record_search(user, "Apartment", {})
        recommendations.record_view(user, listing.id)

        assert RecentSearchActivity.objects.filter(user=user).count() == 1
        assert ListingViewActivity.objects.filter(user=user).count() == 1

        AccountDeletionService.delete_account(user)

        assert RecentSearchActivity.objects.filter(user=user).count() == 0
        assert RecentSearchActivity.global_objects.filter(user=user).count() == 0
        assert ListingViewActivity.objects.filter(user=user).count() == 0
        assert ListingViewActivity.global_objects.filter(user=user).count() == 0


class TestMobileHomeAvailabilityFilters:
    """Mobile feed, map, and inherited favorites honor the availability window."""

    def _available_listing(self, *, today, start, end, with_coordinates: bool = False):
        prop = PropertyFactory(status=PropertyStatus.RENTED)
        listing = ListingFactory(property=prop, status=ListingStatus.PUBLISHED)
        OwnerAgreementFactory(
            property=prop,
            status=OwnerAgreementStatus.ACTIVE,
            start_date=start + timedelta(days=3),
            end_date=end - timedelta(days=3),
        )
        if with_coordinates:
            prop.map_lat = 41.31
            prop.map_lon = 69.28
            prop.save(update_fields=["map_lat", "map_lon"])
        return listing

    def _blocked_listing(self, *, today, start, end):
        prop = PropertyFactory(status=PropertyStatus.RENTED)
        listing = ListingFactory(property=prop, status=ListingStatus.PUBLISHED)
        oa = OwnerAgreementFactory(
            property=prop,
            status=OwnerAgreementStatus.ACTIVE,
            start_date=today,
            end_date=today + timedelta(days=30),
        )
        LeaseFactory(
            property=prop,
            owner_agreement=oa,
            status=LeaseStatus.ACTIVE,
            start_date=today,
            end_date=today + timedelta(days=15),
        )
        return listing

    def test_feed_filters_by_availability(self, api_client):
        today = date.today()
        start = today + timedelta(days=10)
        end = today + timedelta(days=20)

        available = self._available_listing(today=today, start=start, end=end)
        blocked = self._blocked_listing(today=today, start=start, end=end)

        response = api_client.get(LISTINGS_URL, {"start_date": start.isoformat(), "end_date": end.isoformat()})
        assert response.status_code == 200
        ids = {item["id"] for item in _items(response.json())}
        assert available.id in ids
        assert blocked.id not in ids

    def test_feed_map_availability_parity(self, api_client):
        today = date.today()
        start = today + timedelta(days=10)
        end = today + timedelta(days=20)

        available = self._available_listing(today=today, start=start, end=end, with_coordinates=True)
        blocked = self._blocked_listing(today=today, start=start, end=end)
        Property.objects.filter(pk=blocked.property_id).update(map_lat=41.32, map_lon=69.29)

        query = {"start_date": start.isoformat(), "end_date": end.isoformat()}
        feed_response = api_client.get(LISTINGS_URL, query)
        map_response = api_client.get(MAP_URL, {"bbox": "69,41,70,42", **query})

        assert feed_response.status_code == 200
        assert map_response.status_code == 200
        feed_ids = {item["id"] for item in _items(feed_response.json())}
        map_ids = {item["id"] for item in map_response.json()["data"]["items"]}
        assert available.id in feed_ids
        assert available.id in map_ids
        assert blocked.id not in feed_ids
        assert blocked.id not in map_ids
        assert feed_ids == map_ids

    def test_flexibility_narrows_available_window(self, api_client):
        today = date.today()
        start = today + timedelta(days=10)
        end = today + timedelta(days=20)
        # Owner agreement covers only the strict core window (no flexibility slack).
        prop = PropertyFactory(status=PropertyStatus.RENTED)
        listing = ListingFactory(property=prop, status=ListingStatus.PUBLISHED)
        OwnerAgreementFactory(
            property=prop,
            status=OwnerAgreementStatus.ACTIVE,
            start_date=start,
            end_date=end,
        )

        strict = api_client.get(LISTINGS_URL, {"start_date": start.isoformat(), "end_date": end.isoformat()})
        flexible = api_client.get(
            LISTINGS_URL,
            {"start_date": start.isoformat(), "end_date": end.isoformat(), "flexibility_days": 0},
        )
        assert strict.status_code == 200
        assert flexible.status_code == 200
        assert listing.id in {item["id"] for item in _items(strict.json())}
        assert listing.id in {item["id"] for item in _items(flexible.json())}

    def test_missing_one_date_is_rejected(self, api_client):
        today = date.today()
        response = api_client.get(LISTINGS_URL, {"start_date": today.isoformat()})
        assert response.status_code == 400

    def test_reversed_dates_are_rejected(self, api_client):
        today = date.today()
        response = api_client.get(
            LISTINGS_URL,
            {"start_date": (today + timedelta(days=5)).isoformat(), "end_date": today.isoformat()},
        )
        assert response.status_code == 400

    def test_negative_flexibility_is_rejected(self, api_client):
        today = date.today()
        response = api_client.get(
            LISTINGS_URL,
            {
                "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=1)).isoformat(),
                "flexibility_days": -1,
            },
        )
        assert response.status_code == 400
