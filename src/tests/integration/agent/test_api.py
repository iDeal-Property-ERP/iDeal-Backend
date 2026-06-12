import json
from decimal import Decimal

import pytest

from core.constants import AgentDealStatus
from tests.factories import (
    AgentDealFactory,
    AgentFactory,
    AgentProfileFactory,
    DistrictFactory,
    OwnerFactory,
    PropertyFactory,
)


@pytest.mark.django_db
class TestAgentListAPI:
    def test_list_agents(self, api_client, jwt_header):
        agent_user = AgentFactory()
        AgentProfileFactory(user=agent_user)
        agent_user2 = AgentFactory()
        AgentProfileFactory(user=agent_user2)

        response = api_client.get("/api/v1/agents/", **jwt_header)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 2

    def test_list_agents_requires_auth(self, api_client):
        response = api_client.get("/api/v1/agents/")
        assert response.status_code == 401

    def test_list_agents_filter_active(self, api_client, jwt_header):
        agent_user = AgentFactory()
        AgentProfileFactory(user=agent_user, is_active=True)
        agent_user2 = AgentFactory()
        AgentProfileFactory(user=agent_user2, is_active=False)

        response = api_client.get("/api/v1/agents/?is_active=true", **jwt_header)
        assert response.status_code == 200
        body = response.json()
        active_ids = [item["id"] for item in body["data"]]
        assert len(active_ids) >= 1

    def test_list_agents_paginated(self, api_client, jwt_header):
        for _ in range(3):
            agent_user = AgentFactory()
            AgentProfileFactory(user=agent_user)

        response = api_client.get("/api/v1/agents/?page=1&per_page=2", **jwt_header)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["per_page"] == 2
        assert data["page"]["number"] == 1
        assert len(data["page"]["object_list"]) == 2


@pytest.mark.django_db
class TestAgentDetailAPI:
    def test_agent_detail(self, api_client, jwt_header):
        agent_user = AgentFactory(first_name="John")
        agent_profile = AgentProfileFactory(user=agent_user)

        response = api_client.get(f"/api/v1/agents/{agent_profile.id}/", **jwt_header)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["user_name"] == "John"
        assert body["data"]["total_deals"] == 0

    def test_agent_detail_requires_auth(self, api_client):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)

        response = api_client.get(f"/api/v1/agents/{agent_profile.id}/")
        assert response.status_code == 401

    def test_agent_detail_not_found(self, api_client, jwt_header):
        response = api_client.get("/api/v1/agents/99999/", **jwt_header)
        assert response.status_code == 404


@pytest.mark.django_db
class TestAgentDealListAPI:
    def test_list_agent_deals(self, api_client, jwt_header):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner)
        AgentDealFactory(agent=agent_profile, property=prop)
        AgentDealFactory(agent=agent_profile, property=prop)

        response = api_client.get(f"/api/v1/agents/{agent_profile.id}/deals/", **jwt_header)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 2

    def test_list_agent_deals_requires_auth(self, api_client):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)

        response = api_client.get(f"/api/v1/agents/{agent_profile.id}/deals/")
        assert response.status_code == 401

    def test_list_agent_deals_agent_not_found(self, api_client, jwt_header):
        response = api_client.get("/api/v1/agents/99999/deals/", **jwt_header)
        assert response.status_code == 404

    def test_list_agent_deals_paginated(self, api_client, jwt_header):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)
        district = DistrictFactory()
        owner = OwnerFactory()
        for _ in range(3):
            prop = PropertyFactory(district=district, owner=owner)
            AgentDealFactory(agent=agent_profile, property=prop)

        response = api_client.get(f"/api/v1/agents/{agent_profile.id}/deals/?page=1&per_page=2", **jwt_header)
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert data["per_page"] == 2
        assert len(data["page"]["object_list"]) == 2


@pytest.mark.django_db
class TestAgentDealCreateAPI:
    def test_create_agent_deal(self, api_client, jwt_header):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner)

        payload = {
            "property_id": prop.id,
            "deal_date": "2026-06-12",
            "rent_amount": "1000.00",
        }
        response = api_client.post(
            f"/api/v1/agents/{agent_profile.id}/deals/",
            data=json.dumps(payload),
            content_type="application/json",
            **jwt_header,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["agent_id"] == agent_profile.id
        assert body["data"]["property_id"] == prop.id
        assert body["data"]["rent_amount"] == "1000.00"
        assert Decimal(body["data"]["commission_amount"]) == Decimal("100.00")
        assert body["data"]["status"] == AgentDealStatus.CLOSED

    def test_create_agent_deal_requires_auth(self, api_client):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)

        payload = {
            "property_id": 1,
            "deal_date": "2026-06-12",
            "rent_amount": "1000.00",
        }
        response = api_client.post(
            f"/api/v1/agents/{agent_profile.id}/deals/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_create_agent_deal_updates_agent_stats(self, api_client, jwt_header):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user, commission_rate="15.00")
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner)

        payload = {
            "property_id": prop.id,
            "deal_date": "2026-06-12",
            "rent_amount": "2000.00",
        }
        response = api_client.post(
            f"/api/v1/agents/{agent_profile.id}/deals/",
            data=json.dumps(payload),
            content_type="application/json",
            **jwt_header,
        )
        assert response.status_code == 201
        agent_profile.refresh_from_db()
        assert agent_profile.total_deals == 1
        assert agent_profile.total_revenue == 300.00

    def test_create_agent_deal_validation_error(self, api_client, jwt_header):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)

        payload = {
            "property_id": "not_an_int",
            "deal_date": "2026-06-12",
            "rent_amount": "1000.00",
        }
        response = api_client.post(
            f"/api/v1/agents/{agent_profile.id}/deals/",
            data=json.dumps(payload),
            content_type="application/json",
            **jwt_header,
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert "error" in body

    def test_create_agent_deal_agent_not_found(self, api_client, jwt_header):
        payload = {
            "property_id": 1,
            "deal_date": "2026-06-12",
            "rent_amount": "1000.00",
        }
        response = api_client.post(
            "/api/v1/agents/99999/deals/create/",
            data=json.dumps(payload),
            content_type="application/json",
            **jwt_header,
        )
        assert response.status_code == 404
