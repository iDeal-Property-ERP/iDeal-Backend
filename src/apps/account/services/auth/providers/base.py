import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import requests

logger = logging.getLogger(__name__)

OTP_PROVIDER_TIMEOUT = 10


class OTPMessagePurpose(StrEnum):
    LOGIN = "login"
    PHONE_CHANGE = "phone_change"
    ACCOUNT_DELETION = "account_deletion"


@dataclass(frozen=True, slots=True)
class OTPMessage:
    phone: str
    code: str
    purpose: OTPMessagePurpose = OTPMessagePurpose.LOGIN


class OTPDeliveryError(Exception):
    """Raised when an OTP provider cannot accept a verification message."""


class OTPProvider(ABC):
    """Normalized delivery interface shared by all OTP gateways."""

    provider_name = "otp"
    enabled_setting: str = ""

    def __init__(self, *, http_client: Any = requests):
        self.http = http_client

    @property
    def is_enabled(self) -> bool:
        if not self.enabled_setting:
            return True
        from django.conf import settings

        return bool(getattr(settings, self.enabled_setting, False))

    @abstractmethod
    def send(self, message: OTPMessage) -> None:
        """Deliver an OTP message or raise OTPDeliveryError."""

    def _post(self, url: str, **kwargs) -> requests.Response:
        try:
            return self.http.post(url, timeout=OTP_PROVIDER_TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            logger.warning("OTP provider request failed provider=%s", self.provider_name)
            raise OTPDeliveryError from exc

    def _json_payload(self, response: requests.Response) -> dict:
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            logger.warning(
                "OTP provider returned invalid JSON provider=%s status=%s",
                self.provider_name,
                response.status_code,
            )
            raise OTPDeliveryError from exc
        if not isinstance(payload, dict):
            logger.warning(
                "OTP provider returned an unexpected payload provider=%s status=%s",
                self.provider_name,
                response.status_code,
            )
            raise OTPDeliveryError
        return payload

    def _provider_error(self, response: requests.Response) -> OTPDeliveryError:
        logger.warning(
            "OTP provider rejected request provider=%s status=%s",
            self.provider_name,
            response.status_code,
        )
        return OTPDeliveryError("OTP provider error")

    @staticmethod
    def _payload_indicates_error(payload: dict) -> bool:
        status = payload.get("status")
        return (
            payload.get("ok") == False  # noqa: E712
            or payload.get("success") == False  # noqa: E712
            or status == False  # noqa: E712
            or str(status).lower() in {"error", "failed", "fail", "false"}
        )
