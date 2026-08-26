import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.constants import ListingStatus
from tests.factories import DistrictFactory, OwnerFactory, PropertyFactory, PublicOfferFactory
from tests.integration.property.test_api import _make_jwt

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.django_db
class TestOwnerPropertiesAPI:
    def test_owner_sees_own_properties(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()
        PropertyFactory(owner=owner, district=district, name="My Property")
        other_owner = OwnerFactory()
        PropertyFactory(owner=other_owner, district=district, name="Not Mine")
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/properties/", **_make_jwt(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        names = [p["name"] for p in body["data"]]
        assert "My Property" in names
        assert "Not Mine" not in names

    def test_owner_properties_rbac(self, api_client):
        from tests.factories import TenantFactory

        tenant = TenantFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/properties/", **_make_jwt(tenant))
        assert response.status_code == 403

    def test_owner_properties_requires_auth(self, api_client):
        response = api_client.get("/api/v1/owner/properties/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestOwnerEarningsAPI:
    def test_owner_earnings(self, api_client):
        owner = OwnerFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/earnings/", **_make_jwt(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "total_guaranteed" in data
        assert "total_paid" in data
        assert "total_pending" in data
        assert data["currency"] == "USD"

    def test_owner_earnings_rbac(self, api_client):
        from tests.factories import TenantFactory

        tenant = TenantFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/earnings/", **_make_jwt(tenant))
        assert response.status_code == 403


@pytest.mark.django_db
class TestOwnerWhyAPI:
    def test_owner_why(self, api_client):
        owner = OwnerFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/why/", **_make_jwt(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "title" in data
        assert "description" in data
        assert "benefits" in data
        assert isinstance(data["benefits"], list)

    def test_owner_why_rbac(self, api_client):
        from tests.factories import TenantFactory

        tenant = TenantFactory()
        from tests.integration.property.test_api import _make_jwt

        response = api_client.get("/api/v1/owner/why/", **_make_jwt(tenant))
        assert response.status_code == 403

    def test_owner_why_requires_auth(self, api_client):
        response = api_client.get("/api/v1/owner/why/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestOwnerListingWizard:
    def _submit_listing(self, api_client, owner, district, n_photos=5, include_accept_offer=True, **overrides):
        payload = {
            "property_type": "apartment",
            "name": "Bright 2-room near Yunusobod metro",
            "district_id": district.id,
            "rooms": 2,
            "area_sqm": 68,
            "floor": 2,
            "total_floors": 9,
            "furnishing": "furnished",
            "description": "Sunny corner apartment.",
            "monthly_price": "520.00",
            "deposit_amount": "520.00",
            "currency": "USD",
            "amenities": ["wifi", "parking"],
        }
        if include_accept_offer:
            payload["accept_offer"] = True
        payload.update(overrides)
        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(n_photos)]
        return api_client.post(
            "/api/v1/owner/listings/submit/",
            data={"payload": json.dumps(payload), "images": files},
            **_make_jwt(owner),
        )

    def test_submit_listing_atomic(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()
        PublicOfferFactory(version="v1", body="Terms", is_active=True)

        response = self._submit_listing(api_client, owner, district, n_photos=5)
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["status"] == "pending_review"
        assert data["name"].startswith("Bright 2-room")
        assert len(data["photos"]) == 5

        # Must NOT appear on public marketplace before approval
        from marketplace.models import Listing
        from property.models import Property

        listing = Listing.objects.get(pk=data["id"])
        assert listing.is_active is False
        assert Property.objects.get(pk=data["property_id"]).status == "pending_review"

    def test_submit_requires_five_photos(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()
        PublicOfferFactory(version="v1", body="Terms", is_active=True)

        response = self._submit_listing(api_client, owner, district, n_photos=2)
        assert response.status_code == 422

    def test_submit_requires_accept_offer_field(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()

        response = self._submit_listing(
            api_client,
            owner,
            district,
            include_accept_offer=False,
        )

        assert response.status_code == 400
        assert response.json()["success"] is False

    def test_submit_rejects_false_accept_offer(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()

        response = self._submit_listing(
            api_client,
            owner,
            district,
            accept_offer=False,
        )

        assert response.status_code == 400
        assert response.json()["success"] is False

    def test_resubmit_rejected_listing(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()
        PublicOfferFactory(version="v1", body="Terms", is_active=True)

        created = self._submit_listing(api_client, owner, district, n_photos=5).json()["data"]
        listing_id = created["id"]

        # Reject listing
        from marketplace.models import Listing

        listing = Listing.objects.get(pk=listing_id)
        listing.status = ListingStatus.REJECTED
        listing.rejection_reason = "Please fix description and add 1 photo."
        listing.save(update_fields=["status", "rejection_reason", "updated_at"])

        # Resubmit with keep 5 photos + 1 new photo
        kept_ids = [p["id"] for p in created["photos"]]
        resubmit_payload = {
            "property_type": "apartment",
            "name": "Bright 2-room Updated",
            "district_id": district.id,
            "rooms": 2,
            "area_sqm": 68,
            "floor": 2,
            "total_floors": 9,
            "furnishing": "furnished",
            "description": "Updated sunny corner apartment.",
            "monthly_price": "550.00",
            "deposit_amount": "550.00",
            "currency": "USD",
            "keep_photo_ids": kept_ids,
            "accept_offer": True,
        }
        from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart

        new_file = SimpleUploadedFile("p_extra.png", _PNG, content_type="image/png")
        data = encode_multipart(BOUNDARY, {"payload": json.dumps(resubmit_payload), "images": new_file})
        new_file.seek(0)
        resubmit_resp = api_client.put(
            f"/api/v1/owner/listings/{listing_id}/resubmit/",
            data=data,
            content_type=MULTIPART_CONTENT,
            **_make_jwt(owner),
        )
        assert resubmit_resp.status_code == 200
        resubmitted_data = resubmit_resp.json()["data"]
        assert resubmitted_data["status"] == "pending_review"
        assert resubmitted_data["name"] == "Bright 2-room Updated"
        assert len(resubmitted_data["photos"]) == 6

    def test_cannot_resubmit_others_listing(self, api_client):
        owner = OwnerFactory()
        other = OwnerFactory()
        district = DistrictFactory()
        PublicOfferFactory(version="v1", body="Terms", is_active=True)

        created = self._submit_listing(api_client, owner, district, n_photos=5).json()["data"]
        listing_id = created["id"]

        from marketplace.models import Listing

        listing = Listing.objects.get(pk=listing_id)
        listing.status = ListingStatus.REJECTED
        listing.save(update_fields=["status", "updated_at"])

        resubmit_payload = {
            "district_id": district.id,
            "rooms": 2,
            "area_sqm": 68,
            "floor": 2,
            "monthly_price": "550.00",
            "keep_photo_ids": [p["id"] for p in created["photos"]],
            "accept_offer": True,
        }
        response = api_client.put(
            f"/api/v1/owner/listings/{listing_id}/resubmit/",
            data={"payload": json.dumps(resubmit_payload)},
            **_make_jwt(other),
        )
        assert response.status_code in (404, 422)
