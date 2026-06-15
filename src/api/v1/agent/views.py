import pydantic
from agent.models import Agent, AgentDeal
from django.shortcuts import get_object_or_404
from dmr import Body, Path, Query

from api.v1.agent.schemas import AgentDealCreateInput, AgentDealOutput, AgentOutput
from core.api.permissions import RoleAuth
from core.api.views import DetailPath, GenericController, ListAPIView, RetrieveAPIView
from core.constants import UserRole


class AgentListQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20
    is_active: bool | None = None


class AgentListView(ListAPIView):
    model = Agent
    output_schema = AgentOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return Agent.objects.select_related("user").all()

    def get(self, parsed_query: Query[AgentListQuery]) -> dict:
        qs = self.get_queryset()
        if parsed_query.is_active is not None:
            qs = qs.filter(is_active=parsed_query.is_active)
        return self.list_response(qs, parsed_query)


class AgentDetailView(RetrieveAPIView):
    model = Agent
    output_schema = AgentOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return Agent.objects.select_related("user").all()

    def get(self, parsed_path: Path[DetailPath]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        return self.ok(self.to_output(instance))


class AgentDealListQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20


class AgentDealListCreateView(GenericController):
    model = AgentDeal
    output_schema = AgentDealOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return AgentDeal.objects.select_related("agent", "property").all()

    def get(self, parsed_path: Path[DetailPath], parsed_query: Query[AgentDealListQuery]) -> dict:
        agent = get_object_or_404(Agent.objects.all(), pk=parsed_path.pk)
        qs = self.get_queryset().filter(agent=agent)
        return self.list_response(qs, parsed_query)

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[AgentDealCreateInput]) -> dict:
        agent = get_object_or_404(Agent.objects.all(), pk=parsed_path.pk)
        commission_amount = parsed_body.rent_amount * agent.commission_rate / 100
        deal = AgentDeal.objects.create(
            agent=agent,
            property_id=parsed_body.property_id,
            deal_date=parsed_body.deal_date,
            rent_amount=parsed_body.rent_amount,
            commission_amount=commission_amount,
            status=parsed_body.status,
        )
        return self.ok(self.to_output(deal))
