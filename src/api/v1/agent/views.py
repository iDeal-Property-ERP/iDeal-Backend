import pydantic
from agent.models import Agent, AgentDeal
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query

from api.v1.agent.schemas import AgentDealCreateInput, AgentDealOutput, AgentOutput
from core.api.views import DetailPath, GenericController, ListAPIView, RetrieveAPIView
from core.utils.pagination import build_paginated_response


def _build_agent_output(agent):
    return {
        "id": agent.id,
        "user_id": agent.user_id,
        "user_name": agent.user.first_name,
        "total_deals": agent.total_deals,
        "total_revenue": str(agent.total_revenue),
        "commission_rate": str(agent.commission_rate),
        "is_active": agent.is_active,
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
    }


def _build_deal_output(deal):
    return {
        "id": deal.id,
        "agent_id": deal.agent_id,
        "property_id": deal.property_id,
        "property_name": deal.property.name,
        "deal_date": deal.deal_date.isoformat(),
        "rent_amount": str(deal.rent_amount),
        "commission_amount": str(deal.commission_amount),
        "status": deal.status,
        "created_at": deal.created_at.isoformat(),
        "updated_at": deal.updated_at.isoformat(),
    }


class AgentListQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20
    is_active: bool | None = None


class AgentListView(ListAPIView):
    model = Agent
    output_schema = AgentOutput

    def get_queryset(self):
        return Agent.objects.select_related("user").all()

    def get(self, parsed_query: Query[AgentListQuery]) -> dict:
        qs = self.get_queryset()
        if parsed_query.is_active is not None:
            qs = qs.filter(is_active=parsed_query.is_active)
        items = [_build_agent_output(obj) for obj in qs]
        if parsed_query.page is not None:
            paginated = build_paginated_response(items, parsed_query.page, parsed_query.per_page)
            return self.ok(paginated)
        return self.ok(items)


class AgentDetailView(RetrieveAPIView):
    model = Agent
    output_schema = AgentOutput

    def get_queryset(self):
        return Agent.objects.select_related("user").all()

    def get(self, parsed_path: Path[DetailPath]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        return self.ok(_build_agent_output(instance))


class AgentDealListQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20


class AgentDealListCreateView(GenericController):
    model = AgentDeal
    output_schema = AgentDealOutput

    def get_queryset(self):
        return AgentDeal.objects.select_related("agent", "property").all()

    def get(self, parsed_path: Path[DetailPath], parsed_query: Query[AgentDealListQuery]) -> dict:
        agent = get_object_or_404(Agent.objects.all(), pk=parsed_path.pk)
        qs = self.get_queryset().filter(agent=agent)
        items = [_build_deal_output(obj) for obj in qs]
        if parsed_query.page is not None:
            paginated = build_paginated_response(items, parsed_query.page, parsed_query.per_page)
            return self.ok(paginated)
        return self.ok(items)

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[dict]) -> dict:
        agent = get_object_or_404(Agent.objects.all(), pk=parsed_path.pk)
        try:
            validated = AgentDealCreateInput.model_validate(parsed_body)
        except pydantic.ValidationError as err:
            raw_errors = err.errors(include_url=False)
            for e in raw_errors:
                e.pop("ctx", None)
            return self.fail(error=raw_errors, message=str(_("Validation error")))
        commission_amount = validated.rent_amount * agent.commission_rate / 100
        deal = AgentDeal.objects.create(
            agent=agent,
            property_id=validated.property_id,
            deal_date=validated.deal_date,
            rent_amount=validated.rent_amount,
            commission_amount=commission_amount,
            status=validated.status,
        )
        return self.ok(_build_deal_output(deal))
