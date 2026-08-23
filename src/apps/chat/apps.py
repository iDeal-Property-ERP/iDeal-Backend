from django.apps import AppConfig
from django.db.models.signals import post_migrate


def ensure_realtime_schedules(**kwargs):
    """Keep the replay outbox bounded without relying on a web request."""
    from django_q.models import Schedule

    Schedule.objects.update_or_create(
        name="prune-chat-realtime-events",
        defaults={
            "func": "chat.realtime.prune_expired_events",
            "schedule_type": Schedule.DAILY,
            "repeats": -1,
        },
    )


class ChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chat"

    def ready(self):
        post_migrate.connect(ensure_realtime_schedules, sender=self, dispatch_uid="chat_realtime_schedules")
