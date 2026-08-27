from agent.models import AgentDeal
from django.db.models import Count, Sum
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.constants import AgentDealStatus


@receiver(post_save, sender=AgentDeal)
def update_agent_stats_on_deal(sender, instance, created, **kwargs):
    # Recompute from the deals table (excluding cancelled) on every save, so a
    # cancelled deal never inflates performance and totals stay correct across
    # status transitions — not just a blind +1 on create.
    agent = instance.agent
    stats = (
        AgentDeal.objects.filter(agent=agent)
        .exclude(status=AgentDealStatus.CANCELLED)
        .aggregate(
            deals=Count("id"),
            revenue=Sum("commission_amount"),
        )
    )
    agent.total_deals = stats["deals"] or 0
    agent.total_revenue = stats["revenue"] or 0
    agent.save(update_fields=["total_deals", "total_revenue", "updated_at"])
