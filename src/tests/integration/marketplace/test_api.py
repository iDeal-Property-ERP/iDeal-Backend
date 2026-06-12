import json

import pytest

from core.constants import PropertyStatus
from tests.factories import DistrictFactory, PropertyFactory


def _make_vacant_listing(**listing_kwargs):
    prop = PropertyFactory(status=PropertyStatus.VACANT)
    listing = prop.listing
    for k, v in listing_kwargs.items():
        setattr(listing, k, v)
    if listing_kwargs:
        listing.save()
    return listing


@pytest.mark.django_db
class TestPublicListingAPI:
    def test_list_listings_public_no_auth(self, api_client):
        _make_vacant_listing()
        _make_vacant_listing()
        response = api_client.get("/api/v1/marketplace/listings/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 2

    def test_list_listings_only_active_vacant(self, api_client, owner):
        district = DistrictFactory()
        vacant_prop = PropertyFactory(district=district, owner=owner, status=PropertyStatus.VACANT)
        active_listing = vacant_prop.listing

        PropertyFactory(district=district, owner=owner, status=PropertyStatus.RENTED)

        response = api_client.get("/api/v1/marketplace/listings/")
        assert response.status_code == 200
        body = response.json()
        listing_ids = [item["id"] for item in body["data"]]
        assert active_listing.id in listing_ids

    def test_list_listings_paginated(self, api_client):
        for _ in range(5):
            _make_vacant_listing()
        response = api_client.get("/api/v1/marketplace/listings/?page=1&per_page=3")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["per_page"] == 3
        assert data["page"]["number"] == 1
        assert len(data["page"]["object_list"]) == 3

    def test_list_listings_filter_by_district(self, api_client, owner):
        district_a = DistrictFactory(name="Chilonzor")
        district_b = DistrictFactory(name="Sergeli")
        PropertyFactory(district=district_a, owner=owner, status=PropertyStatus.VACANT)
        PropertyFactory(district=district_b, owner=owner, status=PropertyStatus.VACANT)

        response = api_client.get(f"/api/v1/marketplace/listings/?district_id={district_a.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        for item in body["data"]:
            assert item["property"]["district_id"] == district_a.id

    def test_list_listings_filter_by_rooms(self, api_client, owner):
        PropertyFactory(rooms=2, status=PropertyStatus.VACANT)
        PropertyFactory(rooms=3, status=PropertyStatus.VACANT)

        response = api_client.get("/api/v1/marketplace/listings/?rooms=2")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        for item in body["data"]:
            assert item["property"]["rooms"] == 2

    def test_retrieve_listing_public(self, api_client):
        listing = _make_vacant_listing()
        response = api_client.get(f"/api/v1/marketplace/listings/{listing.id}/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["id"] == listing.id
        assert body["data"]["property"] is not None
        assert body["data"]["property"]["name"] == listing.property.name

    def test_retrieve_listing_404(self, api_client):
        response = api_client.get("/api/v1/marketplace/listings/99999/")
        assert response.status_code == 404

    def test_map_endpoint(self, api_client, owner):
        PropertyFactory(map_lat=41.3111, map_lon=69.2797, status=PropertyStatus.VACANT)
        response = api_client.get("/api/v1/marketplace/listings/map/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["type"] == "FeatureCollection"
        assert len(body["data"]["features"]) >= 1

    def test_map_endpoint_excludes_null_coordinates(self, api_client, owner):
        PropertyFactory(map_lat=None, map_lon=None, status=PropertyStatus.VACANT)
        PropertyFactory(map_lat=41.3111, map_lon=69.2797, status=PropertyStatus.VACANT)

        response = api_client.get("/api/v1/marketplace/listings/map/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]["features"]) == 1

    def test_book_viewing_success(self, api_client):
        listing = _make_vacant_listing()
        payload = json.dumps(
            {
                "full_name": "John Doe",
                "phone": "+998901234567",
                "email": "john@example.com",
                "preferred_date": "2025-06-15",
                "message": "I want to view this property.",
            }
        )
        response = api_client.post(
            f"/api/v1/marketplace/listings/{listing.id}/book-viewing/",
            payload,
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["full_name"] == "John Doe"
        assert body["data"]["status"] == "pending"
        assert body["data"]["listing_id"] == listing.id

    def test_book_viewing_validation_error(self, api_client):
        listing = _make_vacant_listing()
        payload = json.dumps({"full_name": "John Doe"})
        response = api_client.post(
            f"/api/v1/marketplace/listings/{listing.id}/book-viewing/",
            payload,
            content_type="application/json",
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert "error" in body

    def test_book_viewing_404(self, api_client):
        payload = json.dumps(
            {
                "full_name": "John Doe",
                "phone": "+998901234567",
                "email": "john@example.com",
                "preferred_date": "2025-06-15",
            }
        )
        response = api_client.post(
            "/api/v1/marketplace/listings/99999/book-viewing/",
            payload,
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_viewing_request_persisted(self, api_client):
        listing = _make_vacant_listing()
        payload = json.dumps(
            {
                "full_name": "Jane Doe",
                "phone": "+998901234568",
                "email": "jane@example.com",
                "preferred_date": "2025-07-01",
            }
        )
        response = api_client.post(
            f"/api/v1/marketplace/listings/{listing.id}/book-viewing/",
            payload,
            content_type="application/json",
        )
        assert response.status_code == 201
        from marketplace.models import ViewingRequest

        vr = ViewingRequest.objects.first()
        assert vr is not None
        assert vr.full_name == "Jane Doe"
        assert vr.listing == listing
