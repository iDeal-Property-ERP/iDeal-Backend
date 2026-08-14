import logging
import secrets
from collections.abc import Mapping

import requests
from account.services.auth.providers.base import OTPDeliveryError, OTPMessage, OTPProvider
from account.services.auth.providers.eskiz import EskizGateway
from account.services.auth.providers.telegram import TelegramGateway
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

OTP_TTL = 300
OTP_ATTEMPT_LIMIT = 5


class OTPService:
    """Manage OTP state and deliver verification codes through supported providers."""

    def __init__(
        self,
        *,
        cache_backend=cache,
        http_client=requests,
        providers: Mapping[str, OTPProvider] | None = None,
    ):
        self.cache = cache_backend
        self.providers = dict(
            providers
            if providers is not None
            else {
                "sms": EskizGateway(cache_backend=cache_backend, http_client=http_client),
                "telegram": TelegramGateway(http_client=http_client),
            }
        )

    @staticmethod
    def generate_otp() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def _otp_cache_key(phone: str, purpose: str) -> str:
        return f"otp:code:{purpose}:{phone}"

    @staticmethod
    def _otp_attempts_cache_key(phone: str, purpose: str) -> str:
        return f"otp_attempts:{purpose}:{phone}"

    def set_otp(self, phone: str, code: str, ttl: int = OTP_TTL, *, purpose: str = "login") -> None:
        self.cache.set(self._otp_cache_key(phone, purpose), code, timeout=ttl)

    def get_otp(self, phone: str, *, purpose: str = "login") -> str | None:
        return self.cache.get(self._otp_cache_key(phone, purpose))

    def pop_otp(self, phone: str, *, purpose: str = "login") -> str | None:
        code = self.get_otp(phone, purpose=purpose)
        self.cache.delete(self._otp_cache_key(phone, purpose))
        return code

    def get_otp_attempts(self, phone: str, *, purpose: str = "login") -> int:
        return int(self.cache.get(self._otp_attempts_cache_key(phone, purpose), 0) or 0)

    def increment_otp_attempts(self, phone: str, ttl: int = OTP_TTL, *, purpose: str = "login") -> int:
        attempts = min(self.get_otp_attempts(phone, purpose=purpose) + 1, OTP_ATTEMPT_LIMIT)
        self.cache.set(self._otp_attempts_cache_key(phone, purpose), attempts, timeout=ttl)
        return attempts

    def clear_otp_attempts(self, phone: str, *, purpose: str = "login") -> None:
        self.cache.delete(self._otp_attempts_cache_key(phone, purpose))

    def dispatch(self, phone: str, code: str, channel: str) -> None:
        if settings.OTP_DEV_BYPASS_CODE:
            logger.info("OTP dev bypass enabled; generated code=%s", code)
            return

        provider = self.providers.get(channel)
        if provider is None:
            raise OTPDeliveryError("Unsupported OTP channel")
        provider.send(OTPMessage(phone=phone, code=code))


__all__ = [
    "OTP_ATTEMPT_LIMIT",
    "OTPDeliveryError",
    "OTPMessage",
    "OTPService",
]
