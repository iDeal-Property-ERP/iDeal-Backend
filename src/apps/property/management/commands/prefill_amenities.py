import logging

from django.core.management.base import BaseCommand
from property.models import Amenity

logger = logging.getLogger(__name__)

AMENITIES = [
    {"slug": "air-conditioning", "name": "Air conditioning", "icon": "wind", "sort_order": 10},
    {"slug": "washing-machine", "name": "Washing machine", "icon": "waves", "sort_order": 20},
    {"slug": "wifi", "name": "Wi-Fi", "icon": "wifi", "sort_order": 30},
    {"slug": "tv", "name": "TV", "icon": "tv", "sort_order": 40},
    {"slug": "balcony", "name": "Balcony", "icon": "sun-medium", "sort_order": 50},
    {"slug": "parking", "name": "Parking", "icon": "car", "sort_order": 60},
    {"slug": "elevator", "name": "Elevator", "icon": "arrow-up-down", "sort_order": 70},
    {"slug": "pet-friendly", "name": "Pet friendly", "icon": "paw-print", "sort_order": 80},
    {"slug": "heating", "name": "Heating", "icon": "thermometer", "sort_order": 90},
    {"slug": "kitchen", "name": "Kitchen", "icon": "utensils", "sort_order": 100},
    {"slug": "workspace", "name": "Workspace", "icon": "laptop", "sort_order": 110},
    {"slug": "gym", "name": "Gym", "icon": "dumbbell", "sort_order": 120},
]


class Command(BaseCommand):
    help = "Prefills the database with common property amenities."

    def handle(self, *args, **options):
        self.stdout.write("Prefilling amenities...")
        created_count = 0
        updated_count = 0

        for amenity_data in AMENITIES:
            obj, created = Amenity.objects.update_or_create(
                slug=amenity_data["slug"],
                defaults={
                    "name": amenity_data["name"],
                    "icon": amenity_data["icon"],
                    "sort_order": amenity_data["sort_order"],
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Successfully created {created_count} amenities and updated {updated_count} amenities.")
        )
