import logging
from threading import Lock

import firebase_admin
from django.conf import settings
from firebase_admin import exceptions, messaging

from .base import PushDeliveryError, PushMessage, PushProvider, PushTokenInvalidError

logger = logging.getLogger(__name__)

_firebase_app = None
_firebase_app_lock = Lock()
_TOKEN_INVALID_EXCEPTIONS = (
    messaging.UnregisteredError,
    messaging.SenderIdMismatchError,
    exceptions.InvalidArgumentError,
)


def _get_app():
    global _firebase_app

    if _firebase_app is not None:
        return _firebase_app

    with _firebase_app_lock:
        if _firebase_app is not None:
            return _firebase_app

        try:
            app = firebase_admin.get_app()
        except ValueError:
            certificate = firebase_admin.credentials.Certificate(settings.FCM_CREDENTIALS_PATH)
            options = {"projectId": settings.FCM_PROJECT_ID} if settings.FCM_PROJECT_ID else None
            try:
                app = firebase_admin.initialize_app(certificate, options)
            except ValueError:
                app = firebase_admin.get_app()

        _firebase_app = app
        return app


class FCMPushProvider(PushProvider):
    """Deliver push messages through Firebase Cloud Messaging."""

    def send(self, message: PushMessage) -> None:
        data = {str(key): str(value) for key, value in message.data.items() if value is not None}

        try:
            fcm_message = messaging.Message(
                notification=messaging.Notification(title=message.title, body=message.body),
                data=data,
                token=message.token,
            )
            messaging.send(fcm_message, app=_get_app())
        except _TOKEN_INVALID_EXCEPTIONS as exc:
            raise PushTokenInvalidError("FCM rejected the device token") from exc
        except PushDeliveryError:
            raise
        except Exception as exc:
            logger.warning("FCM push delivery failed", exc_info=True)
            raise PushDeliveryError("FCM push delivery failed") from exc
