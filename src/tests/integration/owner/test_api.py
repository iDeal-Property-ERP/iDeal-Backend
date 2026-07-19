import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.factories import DistrictFactory, OwnerFactory, PropertyFactory

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
    def _create_draft(self, api_client, owner, district):
        from tests.integration.property.test_api import _make_jwt

        payload = json.dumps(
            {
                "property_type": "apartment",
                "name": "Bright 2-room near Yunusobod metro",
                "district_id": district.id,
                "rooms": 2,
                "area_sqm": 68,
                "furnishing": "furnished",
                "description": "Sunny corner apartment.",
                "amenities": ["wifi", "parking"],
            }
        )
        return api_client.post(
            "/api/v1/owner/listings/",
            data=payload,
            content_type="application/json",
            **_make_jwt(owner),
        )

    def _upload_photos(self, api_client, owner, listing_id, n):
        from tests.integration.property.test_api import _make_jwt

        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(n)]
        return api_client.post(
            f"/api/v1/owner/listings/{listing_id}/photos/",
            data={"images": files},
            **_make_jwt(owner),
        )

    def test_reorder_photos_sets_caption(self, api_client):
        from tests.integration.property.test_api import _make_jwt

        owner = OwnerFactory()
        district = DistrictFactory()
        draft = self._create_draft(api_client, owner, district).json()["data"]
        uploaded = self._upload_photos(api_client, owner, draft["id"], 2).json()["data"]
        pid = uploaded[0]["id"]

        response = api_client.patch(
            f"/api/v1/owner/listings/{draft['id']}/photos/reorder/",
            data=json.dumps({"items": [{"id": pid, "sort_order": 0, "is_primary": True, "caption": "Living room"}]}),
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        photos = response.json()["data"]["photos"]
        assert any(p["id"] == pid and p["caption"] == "Living room" for p in photos)

    def test_create_draft(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()
        response = self._create_draft(api_client, owner, district)
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["status"] == "draft"
        assert data["name"].startswith("Bright 2-room")
        assert {a["slug"] for a in data["amenities"]} == {"wifi", "parking"}
        assert data["completeness"]["has_5_photos"] is False

        # Draft must NOT appear on the public marketplace.
        from marketplace.models import Listing
        from property.models import Property

        listing = Listing.objects.get(pk=data["id"])
        assert listing.is_active is False
        assert Property.objects.get(pk=data["property_id"]).status == "pending_review"

    def test_patch_pricing(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()
        from tests.integration.property.test_api import _make_jwt

        draft = self._create_draft(api_client, owner, district).json()["data"]
        response = api_client.patch(
            f"/api/v1/owner/listings/{draft['id']}/",
            data=json.dumps({"monthly_price": "520.00", "deposit_amount": "520.00", "currency": "USD"}),
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["monthly_price"] == "520.00"
        assert data["completeness"]["has_price"] is True

    def test_full_wizard_submit_then_publish_once(self, api_client):
        """Draft → photos → pricing → submit → management approve → exactly one published listing."""
        from marketplace.models import Listing

        from tests.factories import PublicOfferFactory, UserFactory
        from tests.integration.property.test_api import _make_jwt

        owner = OwnerFactory()
        district = DistrictFactory()
        PublicOfferFactory(version="v1", body="Terms", is_active=True)

        draft = self._create_draft(api_client, owner, district).json()["data"]
        listing_id = draft["id"]

        assert self._upload_photos(api_client, owner, listing_id, 5).status_code == 201
        api_client.patch(
            f"/api/v1/owner/listings/{listing_id}/",
            data=json.dumps({"monthly_price": "520.00", "deposit_amount": "520.00"}),
            content_type="application/json",
            **_make_jwt(owner),
        )

        submit = api_client.post(
            f"/api/v1/owner/listings/{listing_id}/submit/",
            data=json.dumps({"accept_offer": True}),
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert submit.status_code in (200, 201)
        assert submit.json()["data"]["status"] == "pending_review"

        # Management approves the onboarding → property goes vacant → signal publishes the draft.
        from contract.models import OwnerOnboarding

        onboarding = OwnerOnboarding.objects.get(property_id=draft["property_id"])
        mgmt = UserFactory()
        approve = api_client.post(
            f"/api/v1/management/onboardings/{onboarding.id}/approve/",
            data=json.dumps(
                {
                    "commission_rate": "10.00",
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                    "owner_guaranteed_price": "400.00",
                    "tenant_charge_price": "600.00",
                }
            ),
            content_type="application/json",
            **_make_jwt(mgmt),
        )
        assert approve.status_code == 200

        # Exactly one listing exists and it is published (no double-create).
        listings = Listing.objects.filter(property_id=draft["property_id"])
        assert listings.count() == 1
        published = listings.first()
        assert published.status == "published"
        assert published.is_active is True
        assert published.id == listing_id

    def test_submit_requires_five_photos(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()
        from tests.factories import PublicOfferFactory
        from tests.integration.property.test_api import _make_jwt

        PublicOfferFactory(version="v1", body="Terms", is_active=True)
        draft = self._create_draft(api_client, owner, district).json()["data"]
        self._upload_photos(api_client, owner, draft["id"], 2)
        api_client.patch(
            f"/api/v1/owner/listings/{draft['id']}/",
            data=json.dumps({"monthly_price": "520.00", "deposit_amount": "520.00"}),
            content_type="application/json",
            **_make_jwt(owner),
        )
        response = api_client.post(
            f"/api/v1/owner/listings/{draft['id']}/submit/",
            data=json.dumps({"accept_offer": True}),
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 400
        assert response.json()["success"] is False

    def test_wizard_rbac(self, api_client):
        from tests.factories import TenantFactory
        from tests.integration.property.test_api import _make_jwt

        tenant = TenantFactory()
        response = api_client.get("/api/v1/owner/listings/", **_make_jwt(tenant))
        assert response.status_code == 403

    def test_cannot_edit_others_listing(self, api_client):
        owner = OwnerFactory()
        other = OwnerFactory()
        district = DistrictFactory()
        draft = self._create_draft(api_client, owner, district).json()["data"]
        from tests.integration.property.test_api import _make_jwt

        response = api_client.patch(
            f"/api/v1/owner/listings/{draft['id']}/",
            data=json.dumps({"monthly_price": "999.00"}),
            content_type="application/json",
            **_make_jwt(other),
        )
        assert response.status_code == 404
