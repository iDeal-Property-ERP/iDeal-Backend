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


def _items(body):
    """Extract the listing rows from the always-paginated discovery envelope."""
    return body["data"]["page"]["object_list"]


@pytest.mark.django_db
class TestPublicListingAPI:
    def test_list_listings_public_no_auth(self, api_client):
        _make_vacant_listing()
        _make_vacant_listing()
        response = api_client.get("/api/v1/marketplace/listings/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["count"] >= 2
        assert len(_items(body)) >= 2

    def test_list_listings_only_active_vacant(self, api_client, owner):
        district = DistrictFactory()
        vacant_prop = PropertyFactory(district=district, owner=owner, status=PropertyStatus.VACANT)
        active_listing = vacant_prop.listing

        PropertyFactory(district=district, owner=owner, status=PropertyStatus.RENTED)

        response = api_client.get("/api/v1/marketplace/listings/")
        assert response.status_code == 200
        body = response.json()
        listing_ids = [item["id"] for item in _items(body)]
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
        for item in _items(body):
            assert item["property"]["district_id"] == district_a.id

    def test_list_listings_filter_by_rooms(self, api_client, owner):
        PropertyFactory(rooms=2, status=PropertyStatus.VACANT)
        PropertyFactory(rooms=3, status=PropertyStatus.VACANT)

        response = api_client.get("/api/v1/marketplace/listings/?rooms=2")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        for item in _items(body):
            assert item["property"]["rooms"] == 2

    def test_list_listings_filter_verified_only(self, api_client, owner):
        verified = PropertyFactory(owner=owner, status=PropertyStatus.VACANT, is_verified=True)
        PropertyFactory(owner=owner, status=PropertyStatus.VACANT, is_verified=False)

        response = api_client.get("/api/v1/marketplace/listings/?verified=true")
        assert response.status_code == 200
        body = response.json()
        ids = [item["property"]["id"] for item in _items(body)]
        assert verified.id in ids
        assert all(item["property"]["is_verified"] for item in _items(body))

    def test_list_listings_filter_by_amenities(self, api_client, owner):
        from property.models import Amenity

        wifi = Amenity.objects.get(slug="wifi")
        parking = Amenity.objects.get(slug="parking")
        match = PropertyFactory(owner=owner, status=PropertyStatus.VACANT)
        match.amenities.set([wifi, parking])
        partial = PropertyFactory(owner=owner, status=PropertyStatus.VACANT)
        partial.amenities.set([wifi])

        response = api_client.get("/api/v1/marketplace/listings/?amenities=wifi,parking")
        assert response.status_code == 200
        ids = [item["property"]["id"] for item in _items(response.json())]
        assert match.id in ids
        assert partial.id not in ids

    def test_list_listings_sort_price_asc(self, api_client, owner):
        cheap = _make_vacant_listing(monthly_price=300)
        pricey = _make_vacant_listing(monthly_price=900)

        response = api_client.get("/api/v1/marketplace/listings/?sort=price_asc")
        assert response.status_code == 200
        ids = [item["id"] for item in _items(response.json())]
        assert ids.index(cheap.id) < ids.index(pricey.id)

    def test_retrieve_listing_public(self, api_client):
        listing = _make_vacant_listing()
        listing.property.is_verified = True
        listing.property.save(update_fields=["is_verified"])
        response = api_client.get(f"/api/v1/marketplace/listings/{listing.id}/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["id"] == listing.id
        assert data["property"] is not None
        assert data["property"]["name"] == listing.property.name
        assert "score" in data["property"]
        assert data["property"]["review_count"] == listing.property.review_count
        # Enriched detail blocks.
        assert "photos" in data
        assert "contact_phone" in data
        assert data["specs"]["rooms"] == listing.property.rooms
        assert "price_card" in data
        assert data["verification"]["is_verified"] == listing.property.is_verified
        assert len(data["verification"]["checklist"]) == 4

    def test_retrieve_listing_returns_platform_contact_phone(self, api_client):
        listing = _make_vacant_listing()
        from django.test import override_settings

        with override_settings(PLATFORM_CONTACT_PHONE="+998937244041"):
            response = api_client.get(f"/api/v1/marketplace/listings/{listing.id}/")
            assert response.status_code == 200
            assert response.json()["data"]["contact_phone"] == "+998937244041"

    def test_retrieve_listing_hides_verification_checklist_when_unverified(self, api_client):
        listing = _make_vacant_listing()

        response = api_client.get(f"/api/v1/marketplace/listings/{listing.id}/")

        assert response.status_code == 200
        verification = response.json()["data"]["verification"]
        assert verification == {"is_verified": False, "checklist": []}

    def test_retrieve_listing_photo_caption(self, api_client):
        from property.models import PropertyPhoto

        listing = _make_vacant_listing()
        PropertyPhoto.objects.create(
            property=listing.property,
            image="properties/photos/test.jpg",
            caption="Front exterior",
            is_primary=True,
            sort_order=0,
        )
        for i in range(1, 5):
            PropertyPhoto.objects.create(
                property=listing.property,
                image=f"properties/photos/test_{i}.jpg",
                caption=f"Photo {i}",
                is_primary=False,
                sort_order=i,
            )
        response = api_client.get(f"/api/v1/marketplace/listings/{listing.id}/")
        assert response.status_code == 200
        photos = response.json()["data"]["photos"]
        assert photos[0]["caption"] == "Front exterior"

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

    def test_book_viewing_with_time_slot_no_email(self, api_client):
        """Phone-first booking: email omitted, time slot provided."""
        listing = _make_vacant_listing()
        payload = json.dumps(
            {
                "full_name": "Phone Only",
                "phone": "+998900000000",
                "preferred_date": "2025-08-01",
                "preferred_time": "13:00",
            }
        )
        response = api_client.post(
            f"/api/v1/marketplace/listings/{listing.id}/book-viewing/",
            payload,
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["preferred_time"] == "13:00"
        assert body["data"]["email"] is None


@pytest.mark.django_db
class TestMarketplaceLookups:
    def test_districts_endpoint(self, api_client):
        DistrictFactory(name="Yunusobod")
        response = api_client.get("/api/v1/marketplace/districts/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert any(d["name"] == "Yunusobod" for d in body["data"])

    def test_amenities_endpoint_seeded(self, api_client):
        response = api_client.get("/api/v1/marketplace/amenities/")
        assert response.status_code == 200
        body = response.json()
        slugs = {a["slug"] for a in body["data"]}
        assert {"wifi", "parking", "elevator"} <= slugs

    def test_faqs_endpoint_seeded(self, api_client):
        response = api_client.get("/api/v1/marketplace/faqs/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) >= 1
        assert "question" in body["data"][0]

    def test_create_inquiry(self, api_client):
        from notification.models import Notification

        from core.constants import UserRole
        from tests.factories import UserFactory

        listing = _make_vacant_listing()
        manager = UserFactory(role=UserRole.MANAGEMENT)
        payload = json.dumps(
            {
                "listing_id": listing.id,
                "full_name": "Curious Renter",
                "phone": "+998901112233",
                "message": "Is this still available?",
            }
        )
        response = api_client.post(
            "/api/v1/marketplace/inquiries/",
            payload,
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "new"
        assert body["data"]["listing_id"] == listing.id

        from marketplace.models import ContactInquiry

        assert ContactInquiry.objects.filter(full_name="Curious Renter").exists()
        assert Notification.objects.filter(
            recipient=manager,
            related_object_type="contact_inquiry",
            related_object_id=body["data"]["id"],
        ).exists()

    def test_inquiry_normalizes_phone_and_is_rate_limited(self, api_client):
        from django.core.cache import cache

        cache.clear()
        payload = {
            "full_name": "Curious Renter",
            "phone": "998 90 111-22-33",
            "message": "Please contact me.",
        }
        for _ in range(3):
            response = api_client.post(
                "/api/v1/marketplace/inquiries/",
                json.dumps(payload),
                content_type="application/json",
            )
            assert response.status_code == 201
            assert response.json()["data"]["phone"] == "+998901112233"

        limited = api_client.post(
            "/api/v1/marketplace/inquiries/",
            json.dumps(payload),
            content_type="application/json",
        )
        assert limited.status_code == 429
        assert limited.json()["error"] == "rate_limit_exceeded"
