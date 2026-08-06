from datetime import date

from django.core.management.base import BaseCommand, CommandError
from finance.services import ensure_monthly_settlements


class Command(BaseCommand):
    help = "Idempotently creates agreement-month owner settlements through a date."

    def add_arguments(self, parser):
        parser.add_argument("--through", help="Inclusive ISO date; defaults to today.")

    def handle(self, *args, **options):
        try:
            through = date.fromisoformat(options["through"]) if options.get("through") else None
        except ValueError as error:
            raise CommandError("--through must be an ISO date") from error
        created = ensure_monthly_settlements(through)
        self.stdout.write(self.style.SUCCESS(f"Created {created} owner settlement(s)."))
