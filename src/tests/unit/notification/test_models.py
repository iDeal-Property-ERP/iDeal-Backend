import pytest

from core.constants import NotificationCategory
from tests.factories import NotificationPreferenceFactory


@pytest.mark.django_db
def test_notification_preference_master_toggle_blocks_every_category():
    preference = NotificationPreferenceFactory(push_enabled=False)

    assert preference.allows_category(NotificationCategory.PAYMENTS) is False
    assert preference.allows_category(NotificationCategory.GENERAL) is False


@pytest.mark.django_db
def test_notification_preference_category_toggle_only_blocks_that_category():
    preference = NotificationPreferenceFactory(payments_enabled=False)

    assert preference.allows_category(NotificationCategory.PAYMENTS) is False
    assert preference.allows_category(NotificationCategory.BOOKINGS) is True
    assert preference.allows_category(NotificationCategory.GENERAL) is True
