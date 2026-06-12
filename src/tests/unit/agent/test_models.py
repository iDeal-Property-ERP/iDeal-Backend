from decimal import Decimal

import pytest
from agent.models import Agent, AgentDeal

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
class TestAgentModel:
    def test_create_agent(self):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)
        assert agent_profile.id is not None
        assert agent_profile.total_deals == 0
        assert agent_profile.total_revenue == 0
        assert agent_profile.commission_rate == Decimal("10.00")
        assert agent_profile.is_active is True

    def test_agent_str(self):
        agent_user = AgentFactory(first_name="John")
        agent_profile = AgentProfileFactory(user=agent_user)
        assert str(agent_profile) == "Agent: John (deals: 0)"

    def test_agent_user_relation(self):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)
        assert agent_profile.user == agent_user
        assert agent_user.agent_profile == agent_profile

    def test_soft_delete_agent(self):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)
        agent_profile.delete()
        assert Agent.objects.filter(pk=agent_profile.pk).count() == 0
        assert Agent.global_objects.filter(pk=agent_profile.pk).count() == 1


@pytest.mark.django_db
class TestAgentDealModel:
    def test_create_agent_deal(self):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner)
        deal = AgentDealFactory(agent=agent_profile, property=prop, rent_amount=Decimal("1000.00"))
        assert deal.id is not None
        assert deal.status == AgentDealStatus.CLOSED
        assert deal.commission_amount == Decimal("100.00")

    def test_agent_deal_str(self):
        agent_user = AgentFactory(first_name="Alice")
        agent_profile = AgentProfileFactory(user=agent_user)
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner, name="Sunrise Tower")
        deal = AgentDealFactory(agent=agent_profile, property=prop)
        assert str(deal) == f"Deal #{deal.id} — Agent: Alice, Property: Sunrise Tower"

    def test_deal_status_choices(self):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner)
        deal = AgentDealFactory(agent=agent_profile, property=prop)
        deal.status = AgentDealStatus.PENDING
        deal.save(update_fields=["status", "updated_at"])
        deal.refresh_from_db()
        assert deal.status == AgentDealStatus.PENDING

    def test_soft_delete_agent_deal(self):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner)
        deal = AgentDealFactory(agent=agent_profile, property=prop)
        deal.delete()
        assert AgentDeal.objects.filter(pk=deal.pk).count() == 0
        assert AgentDeal.global_objects.filter(pk=deal.pk).count() == 1


@pytest.mark.django_db
class TestAgentDealSignals:
    def test_deal_creation_updates_agent_stats(self):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner)

        assert agent_profile.total_deals == 0
        assert agent_profile.total_revenue == 0

        deal = AgentDealFactory(agent=agent_profile, property=prop, rent_amount=Decimal("1000.00"))
        agent_profile.refresh_from_db()

        assert agent_profile.total_deals == 1
        assert agent_profile.total_revenue == deal.commission_amount
        assert deal.commission_amount == Decimal("100.00")

    def test_commission_amount_calculated_correctly(self):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user, commission_rate=Decimal("15.00"))
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner)

        deal = AgentDealFactory(agent=agent_profile, property=prop, rent_amount=Decimal("2000.00"))
        expected = Decimal("2000.00") * Decimal("15.00") / 100
        assert deal.commission_amount == expected
        assert deal.commission_amount == Decimal("300.00")

    def test_multiple_deals_update_stats_cumulatively(self):
        agent_user = AgentFactory()
        agent_profile = AgentProfileFactory(user=agent_user)
        district = DistrictFactory()
        owner = OwnerFactory()
        prop1 = PropertyFactory(district=district, owner=owner)
        prop2 = PropertyFactory(district=district, owner=owner)

        AgentDealFactory(agent=agent_profile, property=prop1, rent_amount=Decimal("1000.00"))
        agent_profile.refresh_from_db()
        assert agent_profile.total_deals == 1
        assert agent_profile.total_revenue == Decimal("100.00")

        AgentDealFactory(agent=agent_profile, property=prop2, rent_amount=Decimal("500.00"))
        agent_profile.refresh_from_db()
        assert agent_profile.total_deals == 2
        assert agent_profile.total_revenue == Decimal("100.00") + Decimal("50.00")
