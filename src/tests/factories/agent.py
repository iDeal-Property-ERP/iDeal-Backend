from decimal import Decimal

import factory
from agent.models import Agent

from tests.factories.account import AgentFactory as UserAgentFactory


class AgentProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Agent

    user = factory.SubFactory(UserAgentFactory)


class AgentDealFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "agent.AgentDeal"

    agent = factory.SubFactory(AgentProfileFactory)
    property = factory.SubFactory("tests.factories.property.PropertyFactory")
    deal_date = factory.Faker("date_this_year")
    rent_amount = factory.Faker("pydecimal", left_digits=6, right_digits=2, positive=True)

    @factory.lazy_attribute
    def commission_amount(self):
        return Decimal(str(self.rent_amount)) * Decimal(str(self.agent.commission_rate)) / Decimal(100)
