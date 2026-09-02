import json
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from marketplace.models import Listing
from property.models import Property

from core.constants import OneOffDealStatus, PropertyEngagementType, PropertyStatus
from tests.factories import (
    DistrictFactory,
    ExchangeRateFactory,
    OwnerFactory,
)
from tests.integration.property.test_api import _make_jwt

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _create_one_off(api_client, management, **overrides):
    district = DistrictFactory()
    payload = {
        "name": "Mirabad Office 12",
        "address": "12 Amir Temur Ave",
        "district_id": district.id,
        "rooms": 2,
        "area_sqm": 70,
        "floor": 5,
        "total_floors": 9,
        "ask_price": "750.00",
        "seller": {"name": "Seller Snapshot", "phone": "+998901112233"},
        "channel": "marketplace",
        "commission_type": "fixed",
        "commission_fixed_amount": "125.00",
        "commission_currency": "USD",
        **overrides,
    }
    return api_client.post(
        "/api/v1/management/one-off-deals/",
        data=json.dumps(payload),
        content_type="application/json",
        **_make_jwt(management),
    )


@pytest.mark.django_db
class TestOneOffBrokerageAPI:
    def test_action_routes_reject_inherited_get_and_patch(self, api_client):
        action_paths = (
            "activate/",
            "pause/",
            "close-won/",
            "close-lost/",
            "archive/",
            "receipt/",
            "receipt/attachments/",
        )
        for suffix in action_paths:
            path = f"/api/v1/management/one-off-deals/999999/{suffix}"
            assert api_client.get(path).status_code == 405
            assert api_client.patch(path, data="{}", content_type="application/json").status_code == 405

    def test_creates_marketplace_deal_without_owner_account(self, api_client, management):
        response = _create_one_off(api_client, management)

        assert response.status_code == 201
        deal = response.json()["data"]
        prop = Property.objects.get(pk=deal["property_id"])
        assert prop.engagement_type == PropertyEngagementType.ONE_OFF
        assert prop.owner_id is None
        assert deal["status"] == OneOffDealStatus.ACTIVE

    def test_create_one_off_deal_sets_created_by_and_snapshots_contact_phone(self, api_client, management):
        resp_default = _create_one_off(api_client, management, channel="off_market")
        assert resp_default.status_code == 201
        prop_default = Property.objects.get(pk=resp_default.json()["data"]["property_id"])
        assert prop_default.created_by == management
        assert prop_default.contact_phone == management.phone

        resp_custom = _create_one_off(api_client, management, channel="off_market", contact_phone="+998 (97) 111-22-33")
        assert resp_custom.status_code == 201
        prop_custom = Property.objects.get(pk=resp_custom.json()["data"]["property_id"])
        assert prop_custom.created_by == management
        assert prop_custom.contact_phone == "+998971112233"

    def test_closing_archives_listing_and_receipt_reconciles_commission(self, api_client, management):
        ExchangeRateFactory(currency="USD", rate=12500)
        district = DistrictFactory()
        payload = {
            "engagement_type": "one_off",
            "name": "Mirabad Office 12",
            "address": "12 Amir Temur Ave",
            "district_id": district.id,
            "rooms": 2,
            "area_sqm": 70,
            "floor": 5,
            "total_floors": 9,
            "ask_price": "750.00",
            "brokerage": {
                "seller_name": "Seller Snapshot",
                "seller_phone": "+998901112233",
                "channel": "marketplace",
                "commission_type": "fixed",
                "commission_fixed_amount": "125.00",
                "commission_currency": "USD",
            },
        }
        files = [SimpleUploadedFile(f"p{i}.png", _PNG, content_type="image/png") for i in range(5)]
        submit_resp = api_client.post(
            "/api/v1/properties/submit/",
            data={"payload": json.dumps(payload), "images": files},
            **_make_jwt(management),
        )
        print("DEBUG ONE OFF SUBMIT:", submit_resp.status_code, submit_resp.content)
        assert submit_resp.status_code == 201
        prop_data = submit_resp.json()["data"]
        deal_id = prop_data["one_off_deal"]["id"]
        property_id = prop_data["id"]

        # Pause and Reactivate
        paused = api_client.post(
            f"/api/v1/management/one-off-deals/{deal_id}/pause/",
            data="{}",
            content_type="application/json",
            **_make_jwt(management),
        )
        assert paused.status_code == 200

        activated = api_client.post(
            f"/api/v1/management/one-off-deals/{deal_id}/activate/",
            data="{}",
            content_type="application/json",
            **_make_jwt(management),
        )
        assert activated.status_code == 200
        listing = Listing.objects.get(property_id=property_id)
        assert listing.is_active is True

        closed = api_client.post(
            f"/api/v1/management/one-off-deals/{deal_id}/close-won/",
            data=json.dumps(
                {
                    "renter": {"name": "Renter Snapshot", "phone": "+998909998877"},
                    "agreed_monthly_rent": "1000.00",
                    "agreed_currency": "USD",
                    "close_date": date.today().isoformat(),
                    "evidence": [{"filename": "handover.pdf", "url": "https://example.test/handover.pdf"}],
                }
            ),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert closed.status_code == 200
        assert closed.json()["data"]["commission_amount"] == "125.00"
        listing.refresh_from_db()
        assert listing.is_active is False
        assert listing.status == "archived"
        assert Property.objects.get(pk=property_id).status == PropertyStatus.ARCHIVED

        receipt = api_client.post(
            f"/api/v1/management/one-off-deals/{deal_id}/receipt/",
            data=json.dumps(
                {
                    "amount": "125.00",
                    "currency": "USD",
                    "received_date": date.today().isoformat(),
                    "method": "bank_transfer",
                    "reference": "WIRE-001",
                }
            ),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert receipt.status_code == 201
        assert receipt.json()["data"]["receipt"]["reference"] == "WIRE-001"

        attachment = api_client.post(
            f"/api/v1/management/one-off-deals/{deal_id}/receipt/attachments/",
            data={"files": SimpleUploadedFile("wire.pdf", b"%PDF-1.4", content_type="application/pdf")},
            **_make_jwt(management),
        )
        assert attachment.status_code == 201
        attachment_data = attachment.json()["data"]["receipt"]["attachments"]
        assert attachment_data[0]["filename"] == "wire.pdf"
        assert attachment_data[0]["content_type"] == "application/pdf"

        stats = api_client.get("/api/v1/management/brokerage-commissions/stats/", **_make_jwt(management))
        assert stats.status_code == 200
        assert stats.json()["data"]["expected_uzs"] == "1562500.00"
        assert stats.json()["data"]["received_uzs"] == "1562500.00"
        assert stats.json()["data"]["unpaid_uzs"] == "0.00"

    def test_closes_won_without_an_exchange_rate(self, api_client, management):
        created = _create_one_off(api_client, management, channel="off_market").json()["data"]
        deal_id = created["id"]
        closed = api_client.post(
            f"/api/v1/management/one-off-deals/{deal_id}/close-won/",
            data=json.dumps(
                {
                    "renter": {"name": "Renter Snapshot", "phone": "+998909998877"},
                    "agreed_monthly_rent": "1000.00",
                    "agreed_currency": "USD",
                    "close_date": date.today().isoformat(),
                }
            ),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert closed.status_code == 200
        assert closed.json()["data"]["commission_amount"] == "125.00"
        assert closed.json()["data"]["commission_uzs_amount"] is None

    def test_rejects_managed_domain_links_and_engagement_mutation(self, api_client, management):
        created = _create_one_off(api_client, management, channel="off_market").json()["data"]
        property_id = created["property_id"]
        owner = OwnerFactory()

        agreement = api_client.post(
            "/api/v1/contracts/owner-agreements/",
            data=json.dumps(
                {
                    "owner_id": owner.id,
                    "property_id": property_id,
                    "agreement_number": "ONE-OFF-BLOCKED",
                    "signed_date": date.today().isoformat(),
                    "start_date": date.today().isoformat(),
                    "end_date": date.today().replace(year=date.today().year + 1).isoformat(),
                    "commission_rate": "10.00",
                }
            ),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert agreement.status_code == 400

        prop = Property.objects.get(pk=property_id)
        prop.engagement_type = PropertyEngagementType.MANAGED
        with pytest.raises(ValidationError):
            prop.save()


@pytest.mark.django_db
def test_percentage_commission_uses_agreed_rent_snapshot(management):
    from property.models import OneOffDeal

    ExchangeRateFactory(currency="USD", rate=12500)
    district = DistrictFactory()
    prop = Property.objects.create(
        name="Off-market unit",
        address="1 Staff Street",
        district=district,
        rooms=1,
        area_sqm=40,
        floor=2,
        total_floors=5,
        ask_price=Decimal("850.00"),
        engagement_type=PropertyEngagementType.ONE_OFF,
        status=PropertyStatus.VACANT,
    )
    deal = OneOffDeal.objects.create(
        property=prop,
        seller_name="Seller",
        seller_phone="+998901234567",
        channel="off_market",
        status=OneOffDealStatus.ACTIVE,
        commission_type="percentage",
        commission_percentage=Decimal("10.00"),
        commission_currency="USD",
    )
    deal.close_won(
        renter_name="Renter",
        renter_phone="+998907654321",
        renter_email=None,
        agreed_monthly_rent=Decimal("850.00"),
        agreed_currency="USD",
        close_date=date.today(),
        notes="",
        evidence=[],
        closed_by=management,
    )
    deal.refresh_from_db()
    assert deal.commission_amount == Decimal("85.00")
    assert deal.commission_uzs_amount == Decimal("1062500.00")


@pytest.mark.django_db
class TestUnifiedOneOffPropertySubmitAPI:
    def test_one_off_submit_is_atomic_and_rejects_managed_fields(self, api_client, management):
        district = DistrictFactory()
        payload = {
            "engagement_type": "one_off",
            "name": "Off-market unit",
            "address": "1 Staff Street",
            "district_id": district.id,
            "rooms": 1,
            "area_sqm": 40,
            "floor": 2,
            "total_floors": 5,
            "ask_price": "850.00",
            "brokerage": {
                "seller_name": "Seller",
                "seller_phone": "+998901112233",
                "channel": "off_market",
                "commission_type": "none",
            },
        }
        response = api_client.post(
            "/api/v1/properties/submit/",
            data={"payload": json.dumps(payload)},
            **_make_jwt(management),
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["engagement_type"] == PropertyEngagementType.ONE_OFF
        assert data["one_off_deal"]["seller_name"] == "Seller"
        prop = Property.objects.get(pk=data["id"])
        assert prop.owner_id is None

        rejected = api_client.patch(
            f"/api/v1/properties/{prop.id}/one-off/",
            data=json.dumps({"owner_id": OwnerFactory().id}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert rejected.status_code == 400

    def test_off_market_closed_commercial_lock(self, api_client, management):
        district = DistrictFactory()
        payload = {
            "engagement_type": "one_off",
            "name": "Off-market studio",
            "address": "1 Test Street",
            "district_id": district.id,
            "rooms": 1,
            "area_sqm": 40,
            "floor": 2,
            "total_floors": 5,
            "ask_price": "500.00",
            "brokerage": {
                "seller_name": "Seller",
                "seller_phone": "+998901112233",
                "channel": "off_market",
                "commission_type": "fixed",
                "commission_fixed_amount": "80.00",
                "commission_currency": "USD",
            },
        }
        created = api_client.post(
            "/api/v1/properties/submit/",
            data={"payload": json.dumps(payload)},
            **_make_jwt(management),
        )
        assert created.status_code == 201
        data = created.json()["data"]
        deal_id = data["one_off_deal"]["id"]

        closed = api_client.post(
            f"/api/v1/management/one-off-deals/{deal_id}/close-lost/",
            data=json.dumps({"close_date": date.today().isoformat(), "keep_property_active": True}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert closed.status_code == 200

        metadata = api_client.patch(
            f"/api/v1/properties/{data['id']}/one-off/",
            data=json.dumps({"description": "Updated staff-only notes"}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert metadata.status_code == 200
        commercial = api_client.patch(
            f"/api/v1/properties/{data['id']}/one-off/",
            data=json.dumps({"ask_price": "700.00"}),
            content_type="application/json",
            **_make_jwt(management),
        )
        assert commercial.status_code == 400
