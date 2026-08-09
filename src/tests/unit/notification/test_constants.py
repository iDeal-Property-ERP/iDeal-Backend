import pytest

from core.constants import (
    NotificationCategory,
    NotificationType,
    category_for_notification_type,
)


@pytest.mark.parametrize(
    ("notification_type", "expected_category"),
    [
        (NotificationType.PAYMENT_DUE, NotificationCategory.PAYMENTS),
        (NotificationType.PAYMENT_PAID, NotificationCategory.PAYMENTS),
        (NotificationType.PAYOUT_PAID, NotificationCategory.PAYMENTS),
        (NotificationType.BOOKING_STATUS, NotificationCategory.BOOKINGS),
        (NotificationType.SERVICE_REQUEST_STATUS, NotificationCategory.MAINTENANCE),
        (NotificationType.SERVICE_ORDER_STATUS, NotificationCategory.MAINTENANCE),
        (NotificationType.LEASE_RENEWAL, NotificationCategory.LEASES),
        (NotificationType.OWNER_ONBOARDING, NotificationCategory.GENERAL),
        (NotificationType.GENERAL, NotificationCategory.GENERAL),
    ],
)
def test_category_for_notification_type_maps_all_types(notification_type, expected_category):
    assert category_for_notification_type(notification_type) == expected_category


def test_category_for_notification_type_falls_back_to_general():
    assert category_for_notification_type("unknown") == NotificationCategory.GENERAL
