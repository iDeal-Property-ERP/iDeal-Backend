from agent.models import AgentDeal
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=AgentDeal)
def update_agent_stats_on_deal(sender, instance, created, **kwargs):
    if created:
        agent = instance.agent
        agent.total_deals += 1
        agent.total_revenue += instance.commission_amount
        agent.save(update_fields=["total_deals", "total_revenue", "updated_at"])
