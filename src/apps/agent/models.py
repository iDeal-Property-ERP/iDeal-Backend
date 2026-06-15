from django.db import models
from django.utils.translation import gettext_lazy as _

from core.constants import AgentDealStatus
from core.models import SoftDeleteModel, TimestampedModel


class Agent(TimestampedModel, SoftDeleteModel):
    user = models.OneToOneField("account.User", on_delete=models.CASCADE, related_name="agent_profile")
    total_deals = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Agent")
        verbose_name_plural = _("Agents")
        ordering = ["-created_at"]
        db_table = "agents"

    def __str__(self):
        return f"Agent: {self.user.first_name} (deals: {self.total_deals})"


class AgentDeal(TimestampedModel, SoftDeleteModel):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="deals")
    property = models.ForeignKey("property.Property", on_delete=models.PROTECT, related_name="agent_deals")
    deal_date = models.DateField()
    rent_amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=AgentDealStatus.choices, default=AgentDealStatus.CLOSED)

    class Meta:
        verbose_name = _("Agent Deal")
        verbose_name_plural = _("Agent Deals")
        ordering = ["-deal_date"]
        db_table = "agent_deals"
        indexes = [
            models.Index(fields=["agent"]),
            models.Index(fields=["property"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Deal #{self.id} — Agent: {self.agent.user.first_name}, Property: {self.property.name}"
