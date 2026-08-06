from django.utils.translation import gettext_lazy as _


class ConstantChoicesMeta(type):
    """Metaclass to make ConstantChoices classes iterable"""

    def __iter__(cls):
        if hasattr(cls, "CHOICES"):
            return iter(cls.CHOICES)
        return iter([])

    def __len__(cls):
        if hasattr(cls, "CHOICES"):
            return len(cls.CHOICES)
        return 0


class ConstantChoices(metaclass=ConstantChoicesMeta):
    """Base class to make constants behave like Django's TextChoices/IntegerChoices"""

    @classmethod
    def choices(cls):
        return cls.CHOICES if hasattr(cls, "CHOICES") else []

    @classmethod
    def values(cls):
        return [choice[0] for choice in cls.choices()]


class UserRole(ConstantChoices):
    MANAGEMENT = "mgmt"
    OWNER = "owner"
    TENANT = "tenant"
    AGENT = "agent"
    CHOICES = [
        (MANAGEMENT, _("Management")),
        (OWNER, _("Owner")),
        (TENANT, _("Tenant")),
        (AGENT, _("Agent")),
    ]


class PropertyStatus(ConstantChoices):
    DRAFT = "draft"
    RENTED = "rented"
    VACANT = "vacant"
    MAINTENANCE = "maintenance"
    PENDING_REVIEW = "pending_review"
    ARCHIVED = "archived"
    CHOICES = [
        (DRAFT, _("Draft")),
        (RENTED, _("Rented")),
        (VACANT, _("Vacant")),
        (MAINTENANCE, _("Maintenance")),
        (PENDING_REVIEW, _("Pending Review")),
        (ARCHIVED, _("Archived")),
    ]


class PropertyEngagementType(ConstantChoices):
    MANAGED = "managed"
    ONE_OFF = "one_off"
    CHOICES = [
        (MANAGED, _("Managed")),
        (ONE_OFF, _("One-off brokerage")),
    ]


class OneOffChannel(ConstantChoices):
    MARKETPLACE = "marketplace"
    OFF_MARKET = "off_market"
    CHOICES = [
        (MARKETPLACE, _("Marketplace")),
        (OFF_MARKET, _("Off-market")),
    ]


class OneOffDealStatus(ConstantChoices):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
    ARCHIVED = "archived"
    CHOICES = [
        (DRAFT, _("Draft")),
        (ACTIVE, _("Active")),
        (PAUSED, _("Paused")),
        (CLOSED_WON, _("Closed won")),
        (CLOSED_LOST, _("Closed lost")),
        (ARCHIVED, _("Archived")),
    ]


class BrokerageCommissionType(ConstantChoices):
    NONE = "none"
    FIXED = "fixed"
    PERCENTAGE = "percentage"
    CHOICES = [
        (NONE, _("No fee")),
        (FIXED, _("Fixed fee")),
        (PERCENTAGE, _("Percentage of monthly rent")),
    ]


class VerificationVisitStatus(ConstantChoices):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    CHOICES = [
        (SCHEDULED, _("Scheduled")),
        (COMPLETED, _("Completed")),
        (CANCELLED, _("Cancelled")),
    ]


class TariffChoices(ConstantChoices):
    STANDARD = "standard"
    COMFORT = "comfort"
    PREMIUM = "premium"
    CHOICES = [
        (STANDARD, _("Standard")),
        (COMFORT, _("Comfort")),
        (PREMIUM, _("Premium")),
    ]


class PropertyType(ConstantChoices):
    APARTMENT = "apartment"
    HOUSE = "house"
    STUDIO = "studio"
    ROOM = "room"
    CHOICES = [
        (APARTMENT, _("Apartment")),
        (HOUSE, _("House")),
        (STUDIO, _("Studio")),
        (ROOM, _("Room")),
    ]


class FurnishingType(ConstantChoices):
    FURNISHED = "furnished"
    SEMI_FURNISHED = "semi_furnished"
    UNFURNISHED = "unfurnished"
    CHOICES = [
        (FURNISHED, _("Furnished")),
        (SEMI_FURNISHED, _("Semi-furnished")),
        (UNFURNISHED, _("Unfurnished")),
    ]


class MinimumStay(ConstantChoices):
    ONE = 1
    THREE = 3
    SIX = 6
    TWELVE = 12
    CHOICES = [
        (ONE, _("1 month")),
        (THREE, _("3 months")),
        (SIX, _("6 months")),
        (TWELVE, _("12 months")),
    ]


class PriceIncluded(ConstantChoices):
    UTILITIES = "utilities"
    WATER = "water"
    INTERNET = "internet"
    GAS = "gas"
    CLEANING = "cleaning"
    PARKING = "parking"
    CHOICES = [
        (UTILITIES, _("Utilities")),
        (WATER, _("Water")),
        (INTERNET, _("Internet")),
        (GAS, _("Gas")),
        (CLEANING, _("Cleaning")),
        (PARKING, _("Parking")),
    ]


class OwnerAgreementStatus(ConstantChoices):
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    CHOICES = [
        (ACTIVE, _("Active")),
        (EXPIRED, _("Expired")),
        (TERMINATED, _("Terminated")),
    ]


class LeaseStatus(ConstantChoices):
    ACTIVE = "active"
    EXPIRED = "expired"
    RENEWED = "renewed"
    TERMINATED = "terminated"
    CHOICES = [
        (ACTIVE, _("Active")),
        (EXPIRED, _("Expired")),
        (RENEWED, _("Renewed")),
        (TERMINATED, _("Terminated")),
    ]


class PaymentStatus(ConstantChoices):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    CHOICES = [
        (PENDING, _("Pending")),
        (PAID, _("Paid")),
        (OVERDUE, _("Overdue")),
        (CANCELLED, _("Cancelled")),
    ]


class PaymentMethod(ConstantChoices):
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    ONLINE = "online"
    CLICK = "click"
    PAYME = "payme"
    UZUM = "uzum"
    CHOICES = [
        (CASH, _("Cash")),
        (BANK_TRANSFER, _("Bank Transfer")),
        (ONLINE, _("Online")),
        (CLICK, _("Click")),
        (PAYME, _("Payme")),
        (UZUM, _("Uzum")),
    ]


class PaymentKind(ConstantChoices):
    """Classifies cash so deposits never affect owner rent settlements."""

    RENT = "rent"
    DEPOSIT = "deposit"
    OTHER = "other"
    CHOICES = [
        (RENT, _("Rent")),
        (DEPOSIT, _("Deposit")),
        (OTHER, _("Other")),
    ]


class PayoutKind(ConstantChoices):
    BASE = "base"
    UPSIDE_ADJUSTMENT = "upside_adjustment"
    CHOICES = [
        (BASE, _("Base settlement")),
        (UPSIDE_ADJUSTMENT, _("Late rent upside adjustment")),
    ]


class PayoutStatus(ConstantChoices):
    SCHEDULED = "scheduled"
    HELD = "held"
    PAID = "paid"
    CANCELLED = "cancelled"
    CHOICES = [
        (SCHEDULED, _("Scheduled")),
        (HELD, _("Held")),
        (PAID, _("Paid")),
        (CANCELLED, _("Cancelled")),
    ]


class PayoutMethod(ConstantChoices):
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"
    CASH = "cash"
    CHOICES = [
        (BANK_TRANSFER, _("Bank Transfer")),
        (CARD, _("Card")),
        (CASH, _("Cash")),
    ]


class Currency(ConstantChoices):
    USD = "USD"
    UZS = "UZS"
    CHOICES = [
        (USD, _("USD")),
        (UZS, _("UZS")),
    ]


class ServiceRequestStatus(ConstantChoices):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"
    CHOICES = [
        (OPEN, _("Open")),
        (IN_PROGRESS, _("In Progress")),
        (RESOLVED, _("Resolved")),
        (CANCELLED, _("Cancelled")),
    ]


class ServiceRequestPriority(ConstantChoices):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    CHOICES = [
        (LOW, _("Low")),
        (MEDIUM, _("Medium")),
        (HIGH, _("High")),
        (CRITICAL, _("Critical")),
    ]


class CostBearer(ConstantChoices):
    OWNER = "owner"
    PLATFORM = "platform"
    CHOICES = [
        (OWNER, _("Owner")),
        (PLATFORM, _("Platform")),
    ]


class AgentDealStatus(ConstantChoices):
    CLOSED = "closed"
    PENDING = "pending"
    CANCELLED = "cancelled"
    CHOICES = [
        (CLOSED, _("Closed")),
        (PENDING, _("Pending")),
        (CANCELLED, _("Cancelled")),
    ]


class ViewingRequestStatus(ConstantChoices):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    CHOICES = [
        (PENDING, _("Pending")),
        (CONFIRMED, _("Confirmed")),
        (CANCELLED, _("Cancelled")),
    ]


class ViewingTimeSlot(ConstantChoices):
    T_10 = "10:00"
    T_13 = "13:00"
    T_15 = "15:00"
    T_18 = "18:00"
    CHOICES = [
        (T_10, _("10:00")),
        (T_13, _("13:00")),
        (T_15, _("15:00")),
        (T_18, _("18:00")),
    ]


class ListingStatus(ConstantChoices):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    CHOICES = [
        (DRAFT, _("Draft")),
        (PENDING_REVIEW, _("Pending Review")),
        (PUBLISHED, _("Published")),
        (REJECTED, _("Rejected")),
        (ARCHIVED, _("Archived")),
    ]


class ContactInquiryStatus(ConstantChoices):
    NEW = "new"
    HANDLED = "handled"
    CLOSED = "closed"
    CHOICES = [
        (NEW, _("New")),
        (HANDLED, _("Handled")),
        (CLOSED, _("Closed")),
    ]


class OnboardingStatus(ConstantChoices):
    SUBMITTED = "submitted"
    OFFER_ACCEPTED = "offer_accepted"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHOICES = [
        (SUBMITTED, _("Submitted")),
        (OFFER_ACCEPTED, _("Offer Accepted")),
        (APPROVED, _("Approved")),
        (REJECTED, _("Rejected")),
    ]


class InventoryActStatus(ConstantChoices):
    DRAFT = "draft"
    FINALIZED = "finalized"
    CHOICES = [
        (DRAFT, _("Draft")),
        (FINALIZED, _("Finalized")),
    ]


class InventoryActType(ConstantChoices):
    HANDOVER = "handover"
    RETURN = "return"
    GENERAL = "general"
    CHOICES = [
        (HANDOVER, _("Handover")),
        (RETURN, _("Return")),
        (GENERAL, _("General")),
    ]


class ConditionRating(ConstantChoices):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    DAMAGED = "damaged"
    CHOICES = [
        (EXCELLENT, _("Excellent")),
        (GOOD, _("Good")),
        (FAIR, _("Fair")),
        (POOR, _("Poor")),
        (DAMAGED, _("Damaged")),
    ]


class VASServiceType(ConstantChoices):
    CLEANING = "cleaning"
    HANDYMAN = "handyman"
    UTILITY = "utility"
    INTERNET = "internet"
    MOVING = "moving"
    OTHER = "other"
    CHOICES = [
        (CLEANING, _("Cleaning")),
        (HANDYMAN, _("Handyman")),
        (UTILITY, _("Utility")),
        (INTERNET, _("Internet")),
        (MOVING, _("Moving")),
        (OTHER, _("Other")),
    ]


class VASOrderStatus(ConstantChoices):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    CHOICES = [
        (REQUESTED, _("Requested")),
        (CONFIRMED, _("Confirmed")),
        (IN_PROGRESS, _("In Progress")),
        (COMPLETED, _("Completed")),
        (CANCELLED, _("Cancelled")),
    ]


class BookingStatus(ConstantChoices):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONVERTED = "converted"
    CANCELLED = "cancelled"
    CHOICES = [
        (REQUESTED, _("Requested")),
        (APPROVED, _("Approved")),
        (REJECTED, _("Rejected")),
        (CONVERTED, _("Converted")),
        (CANCELLED, _("Cancelled")),
    ]


class NotificationType(ConstantChoices):
    PAYMENT_DUE = "payment_due"
    PAYMENT_PAID = "payment_paid"
    PAYOUT_PAID = "payout_paid"
    BOOKING_STATUS = "booking_status"
    SERVICE_REQUEST_STATUS = "service_request_status"
    LEASE_RENEWAL = "lease_renewal"
    OWNER_ONBOARDING = "owner_onboarding"
    SERVICE_ORDER_STATUS = "service_order_status"
    GENERAL = "general"
    CHOICES = [
        (PAYMENT_DUE, _("Payment Due")),
        (PAYMENT_PAID, _("Payment Paid")),
        (PAYOUT_PAID, _("Payout Paid")),
        (BOOKING_STATUS, _("Booking Status")),
        (SERVICE_REQUEST_STATUS, _("Service Request Status")),
        (LEASE_RENEWAL, _("Lease Renewal")),
        (OWNER_ONBOARDING, _("Owner Onboarding")),
        (SERVICE_ORDER_STATUS, _("Service Order Status")),
        (GENERAL, _("General")),
    ]
