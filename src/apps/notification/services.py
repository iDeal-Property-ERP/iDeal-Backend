"""Notification dispatch — single choke-point for all in-app notifications.

Every feature that needs to notify a user calls :func:`notify`. Today it only
persists an in-app :class:`Notification`. External channels (SMS / Telegram /
email) plug in here later — the ``account.User`` already carries ``telegram_id``
and ``email``.
"""

from notification.models import Notification


def notify(
    *,
    recipient,
    type,
    title,
    body=None,
    related_object_type=None,
    related_object_id=None,
):
    """Create an in-app notification for ``recipient`` and return it."""
    notification = Notification.objects.create(
        recipient=recipient,
        type=type,
        title=title,
        body=body,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
    )
    # TODO: dispatch external channels here (SMS / Telegram / email) using
    # recipient.telegram_id / recipient.email once integrations land.
    return notification
