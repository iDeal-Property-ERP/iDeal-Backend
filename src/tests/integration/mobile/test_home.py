from datetime import timedelta
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
    ListingStatus,
    PropertyEngagementType,
    PropertyStatus,
    PropertyType,
    TariffChoices,
)
from tests.factories import (
    DistrictFactory,
    ListingFactory,
    OwnerAgreementFactory,
    PropertyFactory,
    PropertyPhotoFactory,
)

pytestmark = pytest.mark.django_db

LISTINGS_URL = "/api/v1/mobile/home/listings/"
MAP_URL = "/api/v1/mobile/home/listings/map/"
LISTING_DETAIL_URL = "/api/v1/mobile/home/listings/"
FILTERS_URL = "/api/v1/mobile/home/filters/"


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

    def test_valid_optional_auth_personalizes_is_favorite(self, api_client, tenant):
        from tests.factories import FavoriteListingFactory

        favorite_listing = _make_vacant_listing()
        other_listing = _make_vacant_listing()
        FavoriteListingFactory(user=tenant, listing=favorite_listing)

        response = api_client.get(LISTINGS_URL, **_make_jwt(tenant, jti="valid-home-token"))

        assert response.status_code == 200
        cards = {item["id"]: item for item in _items(response.json()) if item["id"] in {favorite_listing.id, other_listing.id}}
        assert cards[favorite_listing.id]["is_favorite"] is True
        assert cards[other_listing.id]["is_favorite"] is False

    def test_cover_variant_urls_are_absolute_when_present(self, api_client):
        listing = _make_vacant_listing()
        photo = PropertyPhoto.objects.create(
            property=listing.property,
            image="properties/photos/original.jpg",
            is_primary=True,
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
        draft = _make_vacant_listing(status=ListingStatus.DRAFT)
        archived = _make_vacant_listing(status=ListingStatus.ARCHIVED)
        rented_property = PropertyFactory(status=PropertyStatus.RENTED)
        rented = ListingFactory(property=rented_property, status=ListingStatus.PUBLISHED)

        response = api_client.get(LISTINGS_URL)

        assert response.status_code == 200
        ids = {item["id"] for item in _items(response.json())}
        assert visible.id in ids
        assert draft.id not in ids
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


class TestMobileHomeListingMap:
    BBOX = "69,41,70,42"

    @staticmethod
    def _set_coordinates(listing, *, lat=41.31, lon=69.28):
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
        draft = _make_vacant_listing(status=ListingStatus.DRAFT)
        self._set_coordinates(draft)
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
        assert draft.id not in map_ids
        assert archived.id not in map_ids
        assert rented_without_agreement.id not in map_ids

    def test_item_reuses_card_shape_with_non_null_coordinates_and_contact(self, api_client):
        listing = _make_vacant_listing(monthly_price=850, listed_price=900)
        self._set_coordinates(listing)
        photo = PropertyPhoto.objects.create(
            property=listing.property,
            image="properties/photos/map-original.jpg",
            is_primary=True,
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
        listing.property.save(update_fields=["score", "deposit_amount", "description", "updated_at"])
        # Saving the property re-fires manage_listing_on_property_change, which mirrors
        # ask_price/description onto the listing — so set the listing's own values after it.
        listing.refresh_from_db()
        listing.monthly_price = 850
        listing.listed_price = 900
        listing.description = None
        listing.deposit_amount = None
        listing.price_includes = ["utilities"]
        listing.save(
            update_fields=[
                "monthly_price",
                "listed_price",
                "description",
                "deposit_amount",
                "price_includes",
                "updated_at",
            ]
        )

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
            "response_time",
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

        response = api_client.get(f"{LISTING_DETAIL_URL}{listing.id}/")

        assert response.status_code == 200
        photos = response.json()["data"]["photos"]
        assert [photo["id"] for photo in photos] == [primary.id, early.id, late.id]
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
        listing = _make_vacant_listing(status=ListingStatus.DRAFT)

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
        listing = prop.listing
        listing.status = ListingStatus.PUBLISHED
        listing.save(update_fields=["status", "updated_at"])

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
