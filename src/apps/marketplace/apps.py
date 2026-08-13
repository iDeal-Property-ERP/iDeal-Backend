from django.apps import AppConfig
from django.db.models.signals import post_migrate


def ensure_booking_schedules(**kwargs):
    from django_q.models import Schedule

    Schedule.objects.update_or_create(
        name="expire-booking-holds",
        defaults={
            "func": "marketplace.tasks.expire_booking_holds",
            "schedule_type": Schedule.MINUTES,
            "minutes": 1,
            "repeats": -1,
        },
    )
    Schedule.objects.update_or_create(
        name="sync-lease-statuses",
        defaults={
            "func": "marketplace.tasks.sync_lease_statuses",
            "schedule_type": Schedule.MINUTES,
            "minutes": 1,
            "repeats": -1,
        },
    )


class MarketplaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "marketplace"

    def ready(self):
        import marketplace.signals  # noqa: F401

        post_migrate.connect(ensure_booking_schedules, sender=self, dispatch_uid="marketplace_booking_schedules")
