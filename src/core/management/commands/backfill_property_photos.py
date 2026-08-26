"""Attach real-estate stock photos to properties that have none — a local/dev convenience.

The bulk seed (``seed_mock_data --no-images``) created properties without photos, so the public
marketplace renders placeholder cards locally. This finds photo-less properties and adds 5–15
apartment/interior photos each (LoremFlickr by room type, with offline fallbacks) so the gallery
and image viewer have realistic content with room-matched captions. It is idempotent: only
properties with zero photos are touched.

Usage::

    python manage.py backfill_property_photos
    python manage.py backfill_property_photos --listed-only
    python manage.py backfill_property_photos --count 8 --limit 20
"""

from random import Random

from django.core.management import BaseCommand
from django.db import transaction
from django.db.models import Count
from property.models import Property, PropertyPhoto

from core.constants import ListingStatus
from core.mock_images import real_estate_photo_set


class Command(BaseCommand):
    help = "Attach real-estate stock photos to properties that have no PropertyPhoto rows."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=0, help="Photos per property (0 = random 5–12).")
        parser.add_argument(
            "--listed-only",
            action="store_true",
            help="Only properties with an active, published listing (the marketplace-visible set).",
        )
        parser.add_argument("--limit", type=int, default=0, help="Max properties to process (0 = no limit).")

    def handle(self, *args, **options):
        rng = Random()

        qs = Property.objects.annotate(num_photos=Count("photos")).filter(num_photos=0)
        if options["listed_only"]:
            qs = qs.filter(listing__is_active=True, listing__status=ListingStatus.PUBLISHED)
        qs = qs.order_by("id")
        if options["limit"]:
            qs = qs[: options["limit"]]

        properties = list(qs)
        total = len(properties)
        self.stdout.write(f"Backfilling real-estate photos for {total} photo-less properties…")

        done = 0
        for prop in properties:
            count = options["count"] or rng.randint(5, 12)
            with transaction.atomic():  # type: ignore[attr-defined] # pyright: ignore
                for n, (image, caption) in enumerate(real_estate_photo_set(count, rng=rng)):
                    PropertyPhoto.objects.create(
                        property=prop,
                        image=image,
                        caption=caption,
                        is_primary=(n == 0),
                        sort_order=n,
                    )
            done += 1
            if done % 10 == 0 or done == total:
                self.stdout.write(f"  …{done}/{total}")

        self.stdout.write(self.style.SUCCESS(f"Done — added photos to {done} properties."))  # type: ignore[attr-defined] # pyright: ignore
