from django.core.management.base import BaseCommand
from property.models import Amenity, District


class Command(BaseCommand):
    help = "Bootstrap essential data like districts and amenities"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting data bootstrap..."))

        # Add districts (Toshkent City Districts)
        districts = [
            {"name": "Bektemir", "city": "Toshkent"},
            {"name": "Chilonzor", "city": "Toshkent"},
            {"name": "Mirobod", "city": "Toshkent"},
            {"name": "Mirzo Ulugbek", "city": "Toshkent"},
            {"name": "Olmazor", "city": "Toshkent"},
            {"name": "Sergeli", "city": "Toshkent"},
            {"name": "Shayxontohur", "city": "Toshkent"},
            {"name": "Uchtepa", "city": "Toshkent"},
            {"name": "Yakkasaray", "city": "Toshkent"},
            {"name": "Yangihayot", "city": "Toshkent"},
            {"name": "Yashnobod", "city": "Toshkent"},
            {"name": "Yunusabad", "city": "Toshkent"},
        ]

        districts_created = 0
        for data in districts:
            _, created = District.objects.get_or_create(name=data["name"], defaults={"city": data["city"]})
            if created:
                districts_created += 1

        self.stdout.write(
            self.style.SUCCESS(f"Successfully bootstrapped {districts_created} new districts (Total: {len(districts)})")
        )

        # Add amenities (matching lucide icons commonly used)
        amenities = [
            {"slug": "wifi", "name": "Wi-Fi", "icon": "wifi", "sort_order": 10},
            {"slug": "ac", "name": "Air Conditioning", "icon": "wind", "sort_order": 20},
            {"slug": "tv", "name": "TV", "icon": "tv", "sort_order": 30},
            {"slug": "parking", "name": "Parking", "icon": "parking-circle", "sort_order": 40},
            {"slug": "pool", "name": "Pool", "icon": "waves", "sort_order": 50},
            {"slug": "gym", "name": "Gym", "icon": "dumbbell", "sort_order": 60},
            {"slug": "elevator", "name": "Elevator", "icon": "arrow-up-down", "sort_order": 70},
            {"slug": "balcony", "name": "Balcony", "icon": "layout", "sort_order": 80},
            {"slug": "washer", "name": "Washing Machine", "icon": "disc", "sort_order": 90},
            {"slug": "kitchen", "name": "Kitchen", "icon": "chef-hat", "sort_order": 100},
            {"slug": "heating", "name": "Heating", "icon": "flame", "sort_order": 110},
            {"slug": "pets", "name": "Pets Allowed", "icon": "paw-print", "sort_order": 120},
            {"slug": "fridge", "name": "Refrigerator", "icon": "refrigerator", "sort_order": 130},
            {"slug": "furnished", "name": "Furnished", "icon": "sofa", "sort_order": 140},
        ]

        amenities_created = 0
        for data in amenities:
            defaults = data.copy()
            defaults.pop("slug")
            _, created = Amenity.objects.get_or_create(slug=data["slug"], defaults=defaults)
            if created:
                amenities_created += 1

        self.stdout.write(
            self.style.SUCCESS(f"Successfully bootstrapped {amenities_created} new amenities (Total: {len(amenities)})")
        )
        self.stdout.write(self.style.SUCCESS("Bootstrap completed!"))
