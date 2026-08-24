import pydantic
from agent.models import Agent, AgentDeal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from dmr import Body, Path, Query

from api.v1.agent.schemas import (
    AgentCreateInput,
    AgentDealCreateInput,
    AgentDealOutput,
    AgentOutput,
    AgentUpdateInput,
)
from core.api.permissions import RoleAuth
from core.api.views import DetailPath, GenericController, ListAPIView, RetrieveAPIView
from core.constants import AgentDealStatus, UserRole


def _annotated_agent_qs():
    """Agents with per-row deal aggregates (single query, no N+1).

    - ``deals_ytd``: deals created this calendar year
    - ``pending_commission_total``: sum of commission over PENDING deals
    """
    from django.db.models import Count, Q, Sum

    year = timezone.now().year
    return Agent.objects.select_related("user").annotate(
        deals_ytd=Count("deals", filter=Q(deals__created_at__year=year), distinct=True),
        pending_commission_total=Sum("deals__commission_amount", filter=Q(deals__status=AgentDealStatus.PENDING)),
    ).order_by("id")


class AgentListQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20
    is_active: bool | None = None
    has_pending_commission: bool | None = None


class AgentListView(ListAPIView):
    model = Agent
    output_schema = AgentOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return _annotated_agent_qs()

    def get(self, parsed_query: Query[AgentListQuery]) -> dict:
        qs = self.get_queryset()
        if parsed_query.is_active is not None:
            qs = qs.filter(is_active=parsed_query.is_active)
        if parsed_query.has_pending_commission:
            # Exists() keeps the aggregate annotations join-free (a plain
            # deals join here would double-count the Sum annotation).
            from django.db.models import Exists, OuterRef

            pending = AgentDeal.objects.filter(agent_id=OuterRef("pk"), status=AgentDealStatus.PENDING)
            qs = qs.filter(Exists(pending))
        return self.list_response(qs, parsed_query)

    def post(self, parsed_body: Body[AgentCreateInput]) -> dict:
        agent = Agent.objects.create(
            user_id=parsed_body.user_id,
            commission_rate=parsed_body.commission_rate,
            is_active=parsed_body.is_active,
        )
        return self.ok(self.to_output(agent))


class AgentStatsView(GenericController):
    """Saved-view counts for the Agents workbench.

    ``pending_commission`` counts agents that have at least one PENDING deal.
    """

    model = Agent
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get(self) -> dict:
        base = Agent.objects.all()
        return self.ok(
            {
                "counts": {
                    "active": base.filter(is_active=True).count(),
                    "pending_commission": base.filter(deals__status=AgentDealStatus.PENDING).distinct().count(),
                    "all": base.count(),
                }
            }
        )


class AgentDetailView(RetrieveAPIView):
    model = Agent
    output_schema = AgentOutput
    update_schema = AgentUpdateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return _annotated_agent_qs()

    def get(self, parsed_path: Path[DetailPath]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        return self.ok(self.to_output(instance))

    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[AgentUpdateInput]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        instance = self.perform_update(instance, parsed_body.model_dump(exclude_unset=True))
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
