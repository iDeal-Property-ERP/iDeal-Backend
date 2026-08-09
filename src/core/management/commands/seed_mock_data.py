"""Seed the database with realistic, interconnected mock data.

Fills every part of the platform — users of all roles, properties with stock
photos, owner agreements, leases, payments + owner payouts, marketplace
listings/bookings/viewings, maintenance requests, inventory acts, value-added
service orders, agents + deals and notifications.

Design notes
------------
* **Append-only** — this command never flushes. Every run adds a fresh,
  self-consistent batch. All unique fields (``username``, ``email``, ``phone``,
  ``agreement_number``, ``PublicOffer.version``) carry a per-run token so repeat
  runs never collide.
* **Works with existing signals** instead of fighting them:
    - ``marketplace.signals`` auto-creates a :class:`Listing` whenever a property
      is saved VACANT, so listings are *updated*, never created here.
    - ``finance.signals`` auto-accrues a :class:`PayoutSchedule` for every PAID
      payment, so payouts are never created here.
    - ``agent.signals`` auto-updates agent totals on each deal, so totals are
      left untouched.
* Model methods/signals are exercised on purpose (``Lease.save`` flipping a
  property to RENTED, ``OwnerOnboarding.approve``, ``Booking.convert_to_lease``,
  ``Lease.renew``, ``ServiceOrder.save``).

Imports are bare (``from account.models import User``) because ``manage.py``
appends ``src/apps`` to ``sys.path``.

Usage::

    python manage.py seed_mock_data
    python manage.py seed_mock_data --scale large
    python manage.py seed_mock_data --no-images
    python manage.py seed_mock_data --password mypass
"""

import urllib.request
import uuid
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from account.models import User
from agent.models import Agent, AgentDeal
from contract.models import Lease, OwnerAgreement, OwnerOnboarding, PublicOffer
from django.core.files.base import ContentFile
from django.core.management import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker
from finance.models import ExchangeRate, Payment, PayoutSchedule
from inventory.models import InventoryAct, InventoryActItem, InventoryActPhoto
from maintenance.models import ServiceRequest, ServiceRequestPhoto
from marketplace.models import Booking, Listing, ViewingRequest
from notification.models import DeviceToken, Notification, NotificationPreference
from property.models import District, Property, PropertyPhoto
from vas.models import ServiceCatalogItem, ServiceOrder

from core.constants import (
    AgentDealStatus,
    BookingStatus,
    ConditionRating,
    Currency,
    DevicePlatform,
    InventoryActStatus,
    InventoryActType,
    LeaseStatus,
    NotificationAudience,
    NotificationType,
    OwnerAgreementStatus,
    PaymentMethod,
    PaymentStatus,
    PayoutStatus,
    PropertyStatus,
    ServiceRequestPriority,
    ServiceRequestStatus,
    TariffChoices,
    UserRole,
    VASOrderStatus,
    VASServiceType,
    ViewingRequestStatus,
)
from core.mock_images import real_estate_photo_set

# Real Tashkent districts — get_or_create'd so append runs reuse them.
TASHKENT_DISTRICTS = [
    "Yunusobod",
    "Chilonzor",
    "Mirzo Ulug'bek",
    "Yashnobod",
    "Sergeli",
    "Shayxontohur",
    "Olmazor",
    "Uchtepa",
    "Yakkasaroy",
    "Bektemir",
]

# Approximate Tashkent bounding box for plausible map pins.
TASHKENT_LAT = (41.22, 41.38)
TASHKENT_LON = (69.18, 69.40)

INVENTORY_AREAS = [
    "Living Room",
    "Kitchen",
    "Master Bedroom",
    "Second Bedroom",
    "Bathroom",
    "Hallway",
    "Balcony",
]

# (service_type, name, partner, base_price_usd, commission_rate, cashback_rate)
VAS_CATALOG = [
    (VASServiceType.CLEANING, "Standard Apartment Cleaning", "CleanPro", 40, 15, 5),
    (VASServiceType.CLEANING, "Deep Cleaning", "CleanPro", 90, 15, 5),
    (VASServiceType.HANDYMAN, "Minor Repairs Visit", "FixIt Co", 35, 12, 3),
    (VASServiceType.INTERNET, "Home Fibre 100 Mbps", "UzTelecom", 15, 10, 0),
    (VASServiceType.UTILITY, "Utilities Setup & Transfer", "Komunal", 25, 8, 2),
    (VASServiceType.MOVING, "Apartment Moving Service", "MoveEasy", 120, 18, 4),
]

# Stable demo logins, recreated idempotently every run (login is by username).
# (username, role, first_name)
DEMO_ACCOUNTS = [
    ("manager", UserRole.MANAGEMENT, "Demo Manager"),
    ("owner", UserRole.OWNER, "Demo Owner"),
    ("tenant", UserRole.TENANT, "Demo Tenant"),
    ("agent", UserRole.AGENT, "Demo Agent"),
]

SCALES = {
    "small": {"mgmt": 2, "owners": 5, "tenants": 8, "agents": 2},
    "medium": {"mgmt": 5, "owners": 15, "tenants": 25, "agents": 6},
    "large": {"mgmt": 8, "owners": 40, "tenants": 80, "agents": 12},
}

# Models reported in the summary (label, manager). Deltas capture signal-created
# rows (Listing, PayoutSchedule) too.
REPORT_MODELS = [
    ("Districts", District),
    ("Users", User),
    ("Properties", Property),
    ("Property photos", PropertyPhoto),
    ("Owner agreements", OwnerAgreement),
    ("Leases", Lease),
    ("Owner onboardings", OwnerOnboarding),
    ("Public offers", PublicOffer),
    ("Payments", Payment),
    ("Payout schedules", PayoutSchedule),
    ("Exchange rates", ExchangeRate),
    ("Listings", Listing),
    ("Viewing requests", ViewingRequest),
    ("Bookings", Booking),
    ("Service requests", ServiceRequest),
    ("Service request photos", ServiceRequestPhoto),
    ("Inventory acts", InventoryAct),
    ("Inventory items", InventoryActItem),
    ("Inventory photos", InventoryActPhoto),
    ("VAS catalog items", ServiceCatalogItem),
    ("VAS orders", ServiceOrder),
    ("Agents", Agent),
    ("Agent deals", AgentDeal),
    ("Notifications", Notification),
    ("Device tokens", DeviceToken),
    ("Notification preferences", NotificationPreference),
]


class Command(BaseCommand):
    help = "Seed the database with realistic, interconnected mock data (append-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scale",
            choices=list(SCALES),
            default="medium",
            help="Volume of data to generate (default: medium).",
        )
        parser.add_argument(
            "--no-images",
            action="store_true",
            help="Skip downloading stock images and creating photo rows.",
        )
        parser.add_argument(
            "--password",
            default="12345678i",
            help="Shared password for every seeded user (default: 12345678i).",
        )

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        self.scale = options["scale"]
        self.with_images = not options["no_images"]
        self.password = options["password"]
        self.counts = SCALES[self.scale]

        self.token = uuid.uuid4().hex[:6]
        self.faker = Faker()
        Faker.seed(int(self.token, 16))
        self.rng = self.faker.random  # the shared, seeded Random instance
        self._used_phones = set()

        before = {label: model.objects.count() for label, model in REPORT_MODELS}

        self.stdout.write(f"Seeding mock data (scale={self.scale}, images={self.with_images}, token={self.token})…")

        with transaction.atomic():
            districts = self._seed_districts()
            # Stable, memorable demo accounts (idempotent) participate in the data
            # alongside the randomized bulk users so you always have known logins.
            self.demo = self._seed_demo_accounts()
            mgmt = [self.demo[UserRole.MANAGEMENT]] + self._seed_users(UserRole.MANAGEMENT, self.counts["mgmt"])
            owners = [self.demo[UserRole.OWNER]] + self._seed_users(UserRole.OWNER, self.counts["owners"])
            tenants = [self.demo[UserRole.TENANT]] + self._seed_users(
                UserRole.TENANT, self.counts["agents"] + self.counts["tenants"]
            )
            agent_users = [self.demo[UserRole.AGENT]] + self._seed_users(UserRole.AGENT, self.counts["agents"])
            offer = self._seed_public_offer()

            properties = self._seed_properties(owners, districts, mgmt, offer)
            self._seed_leases_and_finance(properties, tenants, mgmt)
            self._seed_exchange_rates()
            self._seed_marketplace(properties, tenants, mgmt)
            self._seed_maintenance(properties, tenants, mgmt)
            self._seed_inventory(properties, mgmt)
            self._seed_vas(properties, tenants)
            self._seed_agents(agent_users, properties)
            self._seed_notifications(owners + tenants + mgmt)

        self._report(before)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _money(self, low, high, currency=Currency.USD):
        if currency == Currency.UZS:
            return Decimal(self.rng.randrange(low * 12000, high * 12000, 50000))
        return Decimal(self.rng.randint(low, high))

    def _days_ago(self, lo, hi):
        return date.today() - timedelta(days=self.rng.randint(lo, hi))

    def _unique_phone(self):
        while True:
            phone = f"+998{self.rng.randint(900000000, 999999999)}"
            if phone not in self._used_phones:
                self._used_phones.add(phone)
                return phone

    def fetch_image(self, seed, width=800, height=600):
        """Return a ``ContentFile`` for a deterministic stock photo.

        Uses Picsum's seeded endpoint so a given ``seed`` always yields the same
        image (keeps an apartment's photo set consistent). Falls back to a tiny
        generated PNG when offline so the command never hard-fails.
        """
        url = f"https://picsum.photos/seed/{seed}/{width}/{height}"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (seed_mock_data)"})
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 (trusted URL)
                return ContentFile(response.read(), name=f"{seed}.jpg")
        except Exception:  # noqa: BLE001 — any network/IO error falls back to a placeholder
            return self._placeholder_png(seed)

    def _placeholder_png(self, seed):
        from PIL import Image

        color = (self.rng.randint(60, 200), self.rng.randint(60, 200), self.rng.randint(60, 200))
        buffer = BytesIO()
        Image.new("RGB", (800, 600), color=color).save(buffer, format="PNG")
        return ContentFile(buffer.getvalue(), name=f"{seed}.png")

    # ------------------------------------------------------------------ #
    # Seeders
    # ------------------------------------------------------------------ #
    def _seed_districts(self):
        districts = []
        for name in TASHKENT_DISTRICTS:
            district, _ = District.objects.get_or_create(name=name, defaults={"city": "Toshkent"})
            districts.append(district)
        return districts

    def _seed_users(self, role, count):
        users = []
        for i in range(count):
            username = f"{role}_{self.token}_{i}"
            user = User.objects.create_user(
                username=username,
                password=self.password,
                email=f"{username}@example.com",
                first_name=self.faker.first_name(),
                last_name=self.faker.last_name(),
                phone=self._unique_phone(),
                role=role,
                is_verified=self.rng.random() < 0.85,
                is_staff=role == UserRole.MANAGEMENT,
                is_superuser=False,
            )
            users.append(user)
        return users

    def _seed_demo_accounts(self):
        """Create/refresh the fixed demo logins. Idempotent across runs.

        Keyed by username so repeat runs reuse the same accounts and simply reset
        the password; they then join the bulk pools to receive data.
        """
        demo = {}
        for username, role, first_name in DEMO_ACCOUNTS:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@ideal.uz",
                    "first_name": first_name,
                    "role": role,
                    "is_verified": True,
                    "is_staff": role == UserRole.MANAGEMENT,
                },
            )
            user.set_password(self.password)
            user.save()
            demo[role] = user
        return demo

    def _seed_public_offer(self):
        return PublicOffer.objects.create(
            version=f"v-{self.token}",
            body=self.faker.paragraph(nb_sentences=8),
            is_active=True,
        )

    def _seed_properties(self, owners, districts, mgmt, offer):
        """Create properties across realistic lifecycle tracks.

        Tracks (weighted): managed-rented, managed-vacant, maintenance,
        onboarding-approved (drives ``approve()``), onboarding-pending
        (submitted/rejected). Listings are auto-created by the marketplace
        signal for every property saved VACANT.
        """
        total = max(len(owners) * 3, 12)
        tracks = self.rng.choices(
            ["rented", "vacant", "maintenance", "onboarding_approved", "onboarding_pending"],
            weights=[34, 26, 10, 18, 12],
            k=total,
        )
        properties = []
        for track in tracks:
            owner = self.rng.choice(owners)
            district = self.rng.choice(districts)
            ask = self._money(300, 1500)
            initial_status = (
                PropertyStatus.PENDING_REVIEW
                if track in ("onboarding_approved", "onboarding_pending")
                else PropertyStatus.VACANT
            )
            total_floors = self.rng.randint(4, 22)
            is_verified = track in ("rented", "vacant") and self.rng.random() < 0.6
            prop = Property.objects.create(
                name=f"{district.name} {self.faker.street_name()} Apt {self.rng.randint(1, 200)}",
                address=self.faker.street_address(),
                district=district,
                rooms=self.rng.randint(1, 5),
                area_sqm=self.rng.randint(28, 180),
                floor=self.rng.randint(1, total_floors),
                total_floors=total_floors,
                owner=owner,
                status=initial_status,
                score=Decimal(f"{self.rng.uniform(8.0, 9.9):.1f}"),
                review_count=self.rng.randint(12, 180),
                is_verified=is_verified,
                verified_at=timezone.now() if is_verified else None,
                map_lat=Decimal(f"{self.rng.uniform(*TASHKENT_LAT):.7f}"),
                map_lon=Decimal(f"{self.rng.uniform(*TASHKENT_LON):.7f}"),
                description=self.faker.paragraph(nb_sentences=4),
                tariff=self.rng.choice([TariffChoices.STANDARD, TariffChoices.COMFORT, TariffChoices.PREMIUM]),
                ask_price=ask,
                owner_guaranteed_price=(ask * Decimal("0.9")).quantize(Decimal("0.01")),
                tenant_charge_price=(ask * Decimal("1.1")).quantize(Decimal("0.01")),
            )
            self._seed_property_photos(prop)

            agreement = None
            if track == "onboarding_approved":
                agreement = self._approve_onboarding(prop, owner, mgmt, offer)
            elif track == "onboarding_pending":
                self._pending_onboarding(prop, owner, mgmt, offer)
            else:
                agreement = self._create_agreement(prop, owner)

            if track == "maintenance":
                prop.status = PropertyStatus.MAINTENANCE
                prop.save(update_fields=["status", "updated_at"])

            properties.append({"obj": prop, "track": track, "agreement": agreement, "want_lease": track in ("rented",)})
            # Half of approved-onboarding properties also get a lease later.
            if track == "onboarding_approved" and self.rng.random() < 0.5:
                properties[-1]["want_lease"] = True

            self._enrich_listing(prop, agreement)
        return properties

    def _seed_property_photos(self, prop):
        if not self.with_images:
            return
        count = self.rng.randint(5, 15)
        for n, (image, caption) in enumerate(real_estate_photo_set(count, rng=self.rng)):
            PropertyPhoto.objects.create(
                property=prop,
                image=image,
                caption=caption,
                is_primary=(n == 0),
                sort_order=n,
            )

    def _create_agreement(self, prop, owner, status=OwnerAgreementStatus.ACTIVE):
        signed = self._days_ago(90, 700)
        return OwnerAgreement.objects.create(
            owner=owner,
            property=prop,
            agreement_number=f"AG-{self.token}-{OwnerAgreement.objects.count() + 1:05d}",
            signed_date=signed,
            start_date=signed,
            end_date=signed + timedelta(days=365),
            status=status,
            terms=self.faker.paragraph(nb_sentences=5),
            commission_rate=Decimal(self.rng.choice([8, 10, 12, 15])),
        )

    def _approve_onboarding(self, prop, owner, mgmt, offer):
        onboarding = OwnerOnboarding.objects.create(owner=owner, property=prop)
        onboarding.accept_offer(offer)
        onboarding.save(update_fields=["offer_version", "offer_terms_snapshot", "offer_accepted_at", "updated_at"])
        start = date.today()
        return onboarding.approve(
            reviewed_by=self.rng.choice(mgmt),
            commission_rate=Decimal(self.rng.choice([10, 12, 15])),
            start_date=start,
            end_date=start + timedelta(days=365),
            agreement_number=f"AG-ONB-{self.token}-{prop.id}",
        )

    def _pending_onboarding(self, prop, owner, mgmt, offer):
        onboarding = OwnerOnboarding.objects.create(owner=owner, property=prop)
        onboarding.accept_offer(offer)
        onboarding.save(update_fields=["offer_version", "offer_terms_snapshot", "offer_accepted_at", "updated_at"])
        if self.rng.random() < 0.3:
            onboarding.reject(reviewed_by=self.rng.choice(mgmt), review_notes="Documents incomplete.")

    def _enrich_listing(self, prop, agreement):
        listing = Listing.objects.filter(property=prop).first()
        if not listing:
            return
        listing.owner_agreement = agreement
        listing.is_featured = self.rng.random() < 0.25
        listing.listed_price = prop.ask_price
        if not listing.description:
            listing.description = prop.description
        listing.save(update_fields=["owner_agreement", "is_featured", "listed_price", "description", "updated_at"])

    def _seed_leases_and_finance(self, properties, tenants, mgmt):
        for entry in properties:
            if not entry["want_lease"] or entry["agreement"] is None:
                continue
            prop = entry["obj"]
            agreement = entry["agreement"]
            tenant = self.rng.choice(tenants)
            start = self._days_ago(60, 400)
            rent = prop.tenant_charge_price
            lease = Lease.objects.create(  # signal flips property -> RENTED
                property=prop,
                owner_agreement=agreement,
                tenant=tenant,
                start_date=start,
                end_date=start + timedelta(days=365),
                monthly_rent=rent,
                deposit=rent,
                status=LeaseStatus.ACTIVE,
            )
            entry["lease"] = lease
            entry["tenant"] = tenant
            self._seed_payments(lease, tenant, mgmt)

            # Occasionally renew an older lease to exercise Lease.renew().
            if self.rng.random() < 0.2:
                new_start = start + timedelta(days=365)
                lease.renew(
                    new_start_date=new_start,
                    new_end_date=new_start + timedelta(days=365),
                    new_monthly_rent=(rent * Decimal("1.08")).quantize(Decimal("0.01")),
                )

    def _seed_payments(self, lease, tenant, mgmt):
        months = min(self._months_between(lease.start_date, date.today()), 12)
        for m in range(months + 1):
            due = self._add_months(lease.start_date, m)
            if due > date.today():
                break
            is_current = self._add_months(due, 1) > date.today()
            status = PaymentStatus.PAID
            payment_date = due
            if is_current:
                status = self.rng.choice([PaymentStatus.PENDING, PaymentStatus.PAID, PaymentStatus.OVERDUE])
                payment_date = due if status == PaymentStatus.PAID else date.today()
            Payment.objects.create(  # PAID status triggers payout accrual signal
                lease=lease,
                tenant=tenant,
                paid_by=self.rng.choice(mgmt) if status == PaymentStatus.PAID else tenant,
                amount=lease.monthly_rent,
                currency=Currency.USD,
                payment_date=payment_date,
                due_date=due,
                status=status,
                method=self.rng.choice([PaymentMethod.CASH, PaymentMethod.BANK_TRANSFER, PaymentMethod.ONLINE]),
                notes=self.faker.sentence() if self.rng.random() < 0.3 else None,
            )
        # Mark a portion of accrued payouts as actually paid out.
        for payout in PayoutSchedule.objects.filter(
            owner_agreement=lease.owner_agreement, status=PayoutStatus.SCHEDULED
        ):
            if self.rng.random() < 0.6:
                payout.status = PayoutStatus.PAID
                payout.paid_date = payout.scheduled_date
                payout.save(update_fields=["status", "paid_date", "updated_at"])

    def _seed_exchange_rates(self):
        for d in range(0, 30, 7):
            effective = date.today() - timedelta(days=d)
            ExchangeRate.objects.create(
                currency=Currency.USD,
                rate=Decimal(f"{self.rng.uniform(12400, 12800):.4f}"),
                effective_date=effective,
            )

    def _seed_marketplace(self, properties, tenants, mgmt):
        listed = [e for e in properties if Listing.objects.filter(property=e["obj"], is_active=True).exists()]
        for entry in listed:
            listing = Listing.objects.get(property=entry["obj"])
            # Viewing requests (prospective, anonymous leads).
            for _ in range(self.rng.randint(0, 3)):
                ViewingRequest.objects.create(
                    listing=listing,
                    full_name=self.faker.name(),
                    phone=f"+998{self.rng.randint(900000000, 999999999)}",
                    email=self.faker.email(),
                    preferred_date=date.today() + timedelta(days=self.rng.randint(1, 21)),
                    message=self.faker.sentence() if self.rng.random() < 0.5 else None,
                    status=self.rng.choice(ViewingRequestStatus.values()),
                )
            # Bookings from logged-in tenants.
            for _ in range(self.rng.randint(0, 2)):
                start = date.today() + timedelta(days=self.rng.randint(3, 30))
                booking = Booking.objects.create(
                    listing=listing,
                    property=entry["obj"],
                    tenant=self.rng.choice(tenants),
                    requested_start_date=start,
                    requested_end_date=start + timedelta(days=365),
                    monthly_rent_offer=entry["obj"].tenant_charge_price,
                    status=self.rng.choice([BookingStatus.REQUESTED, BookingStatus.APPROVED, BookingStatus.REJECTED]),
                    message=self.faker.sentence() if self.rng.random() < 0.6 else None,
                )
                # Convert a few approved bookings into real leases.
                if booking.status == BookingStatus.APPROVED and entry["agreement"] and self.rng.random() < 0.5:
                    booking.convert_to_lease(reviewed_by=self.rng.choice(mgmt))

    def _seed_maintenance(self, properties, tenants, mgmt):
        leased = [e for e in properties if e.get("lease")]
        for entry in leased:
            for n in range(self.rng.randint(0, 3)):
                status = self.rng.choice(ServiceRequestStatus.values())
                resolved = status == ServiceRequestStatus.RESOLVED
                request = ServiceRequest.objects.create(
                    property=entry["obj"],
                    tenant=entry["tenant"],
                    assigned_to=self.rng.choice(mgmt) if self.rng.random() < 0.7 else None,
                    title=self.faker.sentence(nb_words=5).rstrip("."),
                    description=self.faker.paragraph(nb_sentences=3),
                    priority=self.rng.choice(ServiceRequestPriority.values()),
                    status=status,
                    cost=self._money(20, 400) if resolved else None,
                    resolution_notes=self.faker.sentence() if resolved else None,
                )
                if self.with_images and self.rng.random() < 0.5:
                    ServiceRequestPhoto.objects.create(
                        service_request=request,
                        image=self.fetch_image(f"{self.token}-sr{request.id}-{n}", 640, 480),
                    )

    def _seed_inventory(self, properties, mgmt):
        leased = [e for e in properties if e.get("lease")]
        for entry in leased:
            if self.rng.random() < 0.4:
                continue
            finalized = self.rng.random() < 0.6
            act = InventoryAct.objects.create(
                property=entry["obj"],
                lease=entry["lease"],
                act_type=InventoryActType.HANDOVER,
                status=InventoryActStatus.FINALIZED if finalized else InventoryActStatus.DRAFT,
                created_by=self.rng.choice(mgmt),
                notes=self.faker.sentence(),
                finalized_at=timezone.now() if finalized else None,
                acknowledged_by_name=(
                    f"{entry['tenant'].first_name} {entry['tenant'].last_name or ''}".strip() if finalized else None
                ),
                acknowledged_at=timezone.now() if finalized else None,
            )
            areas = self.rng.sample(INVENTORY_AREAS, k=self.rng.randint(3, len(INVENTORY_AREAS)))
            for order, area in enumerate(areas):
                item = InventoryActItem.objects.create(
                    act=act,
                    area=area,
                    condition=self.rng.choice(ConditionRating.values()),
                    notes=self.faker.sentence() if self.rng.random() < 0.4 else None,
                    sort_order=order,
                )
                if self.with_images and self.rng.random() < 0.4:
                    InventoryActPhoto.objects.create(
                        act=act,
                        item=item,
                        image=self.fetch_image(f"{self.token}-inv{act.id}-{order}", 640, 480),
                        caption=area,
                    )

    def _seed_vas(self, properties, tenants):
        catalog = [
            ServiceCatalogItem.objects.create(
                service_type=service_type,
                name=name,
                partner_name=partner,
                description=self.faker.sentence(),
                base_price=Decimal(price),
                currency=Currency.USD,
                commission_rate=Decimal(commission),
                cashback_rate=Decimal(cashback),
            )
            for service_type, name, partner, price, commission, cashback in VAS_CATALOG
        ]
        leased = [e for e in properties if e.get("lease")]
        for entry in leased:
            for _ in range(self.rng.randint(0, 2)):
                item = self.rng.choice(catalog)
                ServiceOrder.objects.create(  # save() derives commission/cashback
                    catalog_item=item,
                    tenant=entry["tenant"],
                    property=entry["obj"],
                    lease=entry["lease"],
                    status=self.rng.choice(VASOrderStatus.values()),
                    cost=item.base_price,
                    currency=item.currency,
                    scheduled_for=date.today() + timedelta(days=self.rng.randint(1, 14)),
                    notes=self.faker.sentence() if self.rng.random() < 0.3 else None,
                )

    def _seed_agents(self, agent_users, properties):
        all_props = [e["obj"] for e in properties]
        for user in agent_users:
            # get_or_create because the demo agent persists across runs (OneToOne).
            agent, _ = Agent.objects.get_or_create(
                user=user,
                defaults={"commission_rate": Decimal(self.rng.choice([8, 10, 12]))},
            )
            for _ in range(self.rng.randint(1, 5)):
                rent = self._money(300, 1500)
                AgentDeal.objects.create(  # signal updates agent totals
                    agent=agent,
                    property=self.rng.choice(all_props),
                    deal_date=self._days_ago(1, 300),
                    rent_amount=rent,
                    commission_amount=(rent * agent.commission_rate / Decimal("100")).quantize(Decimal("0.01")),
                    status=self.rng.choice(AgentDealStatus.values()),
                )

    def _seed_notifications(self, users):
        types = NotificationType.values()
        audiences = [NotificationAudience.MOBILE, NotificationAudience.ERP, NotificationAudience.BOTH]
        for user in users:
            preference, _ = NotificationPreference.objects.get_or_create(
                user=user,
                defaults={
                    "push_enabled": self.rng.random() >= 0.15,
                    "payments_enabled": self.rng.random() >= 0.10,
                    "bookings_enabled": self.rng.random() >= 0.10,
                    "maintenance_enabled": self.rng.random() >= 0.10,
                    "leases_enabled": self.rng.random() >= 0.10,
                    "general_enabled": self.rng.random() >= 0.10,
                },
            )
            if preference.push_enabled:
                DeviceToken.objects.create(
                    user=user,
                    token=f"mock-fcm-{self.token}-{user.pk}-{uuid.uuid4().hex}",
                    platform=self.rng.choice([DevicePlatform.ANDROID, DevicePlatform.IOS]),
                    device_id=f"mock-device-{self.token}-{user.pk}",
                    app_version="1.0.0-mock",
                    locale=self.rng.choice(["en", "ru", "uz"]),
                    is_active=True,
                    last_seen_at=timezone.now() - timedelta(minutes=self.rng.randint(0, 60 * 24 * 14)),
                )
            for _ in range(self.rng.randint(1, 4)):
                read = self.rng.random() < 0.4
                Notification.objects.create(
                    recipient=user,
                    type=self.rng.choice(types),
                    audience=self.rng.choice(audiences),
                    title=self.faker.sentence(nb_words=5).rstrip("."),
                    body=self.faker.paragraph(nb_sentences=2),
                    is_read=read,
                    read_at=timezone.now() if read else None,
                )

    # ------------------------------------------------------------------ #
    # Date utilities
    # ------------------------------------------------------------------ #
    @staticmethod
    def _months_between(start, end):
        return (end.year - start.year) * 12 + (end.month - start.month)

    @staticmethod
    def _add_months(d, months):
        month = d.month - 1 + months
        year = d.year + month // 12
        month = month % 12 + 1
        day = min(d.day, [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        return date(year, month, day)

    # ------------------------------------------------------------------ #
    # Reporting
    # ------------------------------------------------------------------ #
    def _report(self, before):
        self.stdout.write(self.style.SUCCESS(f"\nSeeded (append) — scale={self.scale}"))
        width = max(len(label) for label, _ in REPORT_MODELS)
        for label, model in REPORT_MODELS:
            delta = model.objects.count() - before[label]
            self.stdout.write(f"  {label.ljust(width)}  +{delta}")

        self.stdout.write(self.style.SUCCESS("\nDemo logins — sign in by USERNAME (not email)"))
        self.stdout.write(f"  password: {self.password}")
        for username, role, _ in DEMO_ACCOUNTS:
            self.stdout.write(f"  {role.ljust(6)}: {username}")
