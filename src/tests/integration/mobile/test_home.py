from urllib.parse import urlparse

import pytest
from marketplace.models import Listing
from property.models import PropertyPhoto

from core.constants import FurnishingType, ListingStatus, PropertyStatus, TariffChoices
from tests.factories import DistrictFactory, ListingFactory, PropertyFactory

pytestmark = pytest.mark.django_db

LISTINGS_URL = "/api/v1/mobile/home/listings/"
FILTERS_URL = "/api/v1/mobile/home/filters/"


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
            "map_lat",
            "map_lon",
        }
        assert card["property_id"] == listing.property_id
        assert card["title"] == listing.property.name
        assert card["price"] == 850.0
        assert isinstance(card["price"], float)
        assert isinstance(card["score"], float)
        assert card["cover_image_url"].startswith(("http://", "https://"))
        assert urlparse(card["cover_image_url"]).path.endswith("cover.jpg")

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
        assert set(data) == {"districts", "tariffs", "furnishings", "price", "rooms"}
        assert any(district["name"] == "Filters District" for district in data["districts"])
        assert data["tariffs"] == [{"value": value, "label": str(label)} for value, label in TariffChoices.CHOICES]
        assert data["furnishings"] == [
            {"value": value, "label": str(label)} for value, label in FurnishingType.CHOICES
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
