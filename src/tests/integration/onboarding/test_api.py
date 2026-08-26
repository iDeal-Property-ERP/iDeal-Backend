import json
from decimal import Decimal

import pytest
from contract.models import OwnerAgreement, OwnerOnboarding
from notification.models import Notification

from core.constants import ListingStatus, NotificationType, OnboardingStatus, PropertyStatus
from tests.factories import (
    DistrictFactory,
    ListingFactory,
    OwnerFactory,
    OwnerOnboardingFactory,
    PropertyFactory,
    PublicOfferFactory,
    TenantFactory,
    UserFactory,
)
from tests.integration.property.test_api import _make_jwt


@pytest.mark.django_db
class TestOwnerPublicOffer:
    def test_get_active_offer(self, api_client):
        owner = OwnerFactory()
        PublicOfferFactory(version="v1", body="Terms here", is_active=True)

        response = api_client.get("/api/v1/owner/public-offer/", **_make_jwt(owner))

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["version"] == "v1"
        assert data["body"] == "Terms here"

    def test_no_active_offer(self, api_client):
        owner = OwnerFactory()
        response = api_client.get("/api/v1/owner/public-offer/", **_make_jwt(owner))
        assert response.status_code == 200
        assert response.json()["data"]["version"] is None


@pytest.mark.django_db
class TestOwnerOnboardingSubmit:
    def _payload(self, district, **overrides):
        data = {
            "name": "My Flat",
            "address": "10 Main St",
            "district_id": district.id,
            "rooms": 2,
            "area_sqm": 60,
            "floor": 4,
            "ask_price": "500.00",
            "accept_offer": True,
        }
        data.update(overrides)
        return json.dumps(data)

    def test_submit_creates_pending_property_and_onboarding(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()
        PublicOfferFactory(version="v1", body="Terms", is_active=True)

        response = api_client.post(
            "/api/v1/owner/onboarding/",
            data=self._payload(district),
            content_type="application/json",
            **_make_jwt(owner),
        )

        assert response.status_code in (200, 201)
        onboarding = OwnerOnboarding.objects.get(owner=owner)
        assert onboarding.status == OnboardingStatus.SUBMITTED
        assert onboarding.offer_version == "v1"
        assert onboarding.offer_accepted_at is not None
        assert onboarding.property.status == PropertyStatus.PENDING_REVIEW
        # PENDING_REVIEW property must NOT be auto-listed on the marketplace.
        assert not hasattr(onboarding.property, "listing") or onboarding.property.listing is None

    def test_submit_requires_offer_acceptance(self, api_client):
        owner = OwnerFactory()
        district = DistrictFactory()

        response = api_client.post(
            "/api/v1/owner/onboarding/",
            data=self._payload(district, accept_offer=False),
            content_type="application/json",
            **_make_jwt(owner),
        )

        assert response.status_code == 400
        assert response.json()["success"] is False

    @pytest.mark.parametrize(("field", "value"), [("rooms", 0), ("rooms", -1), ("area_sqm", 0), ("area_sqm", -1)])
    def test_submit_rejects_non_positive_rooms_and_area(self, api_client, field, value):
        owner = OwnerFactory()
        district = DistrictFactory()

        response = api_client.post(
            "/api/v1/owner/onboarding/",
            data=self._payload(district, **{field: value}),
            content_type="application/json",
            **_make_jwt(owner),
        )

        assert response.status_code == 400
        assert response.json()["success"] is False

    def test_submit_rbac(self, api_client):
        tenant = TenantFactory()
        district = DistrictFactory()
        response = api_client.post(
            "/api/v1/owner/onboarding/",
            data=self._payload(district),
            content_type="application/json",
            **_make_jwt(tenant),
        )
        assert response.status_code == 403

    def test_owner_lists_own_onboardings(self, api_client):
        owner = OwnerFactory()
        other = OwnerFactory()
        OwnerOnboardingFactory(owner=owner, property=PropertyFactory(owner=owner))
        OwnerOnboardingFactory(owner=other, property=PropertyFactory(owner=other))

        response = api_client.get("/api/v1/owner/onboarding/", **_make_jwt(owner))

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["owner_id"] == owner.id


@pytest.mark.django_db
class TestManagementOnboardingReview:
    def test_approve_generates_agreement_and_frees_property(self, api_client):
        mgmt = UserFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, status=PropertyStatus.PENDING_REVIEW)
        ListingFactory(property=prop, status=ListingStatus.PENDING_REVIEW, is_active=False)
        onboarding = OwnerOnboardingFactory(owner=owner, property=prop)

        payload = {
            "commission_rate": "10.00",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "owner_guaranteed_price": "400.00",
            "tenant_charge_price": "600.00",
        }
        response = api_client.post(
            f"/api/v1/management/onboardings/{onboarding.id}/approve/",
            data=json.dumps(payload),
            content_type="application/json",
            **_make_jwt(mgmt),
        )

        assert response.status_code == 200
        onboarding.refresh_from_db()
        prop.refresh_from_db()
        assert onboarding.status == OnboardingStatus.APPROVED
        assert onboarding.generated_agreement_id is not None
        assert prop.status == PropertyStatus.VACANT
        assert prop.owner_guaranteed_price == Decimal("400.00")
        assert prop.tenant_charge_price == Decimal("600.00")
        agreement = OwnerAgreement.objects.get(id=onboarding.generated_agreement_id)
        assert agreement.commission_rate == Decimal("10.00")
        # Approving a now-vacant property auto-lists it on the marketplace.
        prop.refresh_from_db()
        assert prop.listing.is_active is True
        assert Notification.objects.filter(recipient=owner, type=NotificationType.OWNER_ONBOARDING).exists()

    def test_reject_sets_status(self, api_client):
        mgmt = UserFactory()
        owner = OwnerFactory()
        onboarding = OwnerOnboardingFactory(owner=owner, property=PropertyFactory(owner=owner))

        response = api_client.post(
            f"/api/v1/management/onboardings/{onboarding.id}/reject/",
            data=json.dumps({"review_notes": "Incomplete documents"}),
            content_type="application/json",
            **_make_jwt(mgmt),
        )

        assert response.status_code == 200
        onboarding.refresh_from_db()
        assert onboarding.status == OnboardingStatus.REJECTED
        assert onboarding.review_notes == "Incomplete documents"

    def test_approve_rbac(self, api_client):
        owner = OwnerFactory()
        onboarding = OwnerOnboardingFactory(owner=owner, property=PropertyFactory(owner=owner))
        response = api_client.post(
            f"/api/v1/management/onboardings/{onboarding.id}/approve/",
            data=json.dumps({"commission_rate": "10.00", "start_date": "2026-01-01", "end_date": "2026-12-31"}),
            content_type="application/json",
            **_make_jwt(owner),
        )
        assert response.status_code == 403

    def test_management_lists_onboardings(self, api_client):
        mgmt = UserFactory()
        OwnerOnboardingFactory()
        OwnerOnboardingFactory()

        response = api_client.get("/api/v1/management/onboardings/", **_make_jwt(mgmt), data={"page": 1})

        assert response.status_code == 200
