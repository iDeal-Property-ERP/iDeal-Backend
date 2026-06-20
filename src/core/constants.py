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
    RENTED = "rented"
    VACANT = "vacant"
    MAINTENANCE = "maintenance"
    PENDING_REVIEW = "pending_review"
    CHOICES = [
        (RENTED, _("Rented")),
        (VACANT, _("Vacant")),
        (MAINTENANCE, _("Maintenance")),
        (PENDING_REVIEW, _("Pending Review")),
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
    CHOICES = [
        (CASH, _("Cash")),
        (BANK_TRANSFER, _("Bank Transfer")),
        (ONLINE, _("Online")),
    ]


class PayoutStatus(ConstantChoices):
    SCHEDULED = "scheduled"
    PAID = "paid"
    CANCELLED = "cancelled"
    CHOICES = [
        (SCHEDULED, _("Scheduled")),
        (PAID, _("Paid")),
        (CANCELLED, _("Cancelled")),
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
