from dataclasses import FrozenInstanceError

import pytest
from account.services.auth.otp import OTP_ATTEMPT_LIMIT, OTPDeliveryError, OTPMessage, OTPProvider, OTPService
from django.test import override_settings


class FakeCache:
    def __init__(self):
        self.values = {}
        self.writes = []

    def set(self, key, value, timeout=None):
        self.values[key] = value
        self.writes.append((key, value, timeout))

    def get(self, key, default=None):
        return self.values.get(key, default)

    def delete(self, key):
        return self.values.pop(key, None)


class RecordingProvider(OTPProvider):
    provider_name = "recording"

    def __init__(self):
        super().__init__(http_client=object())
        self.messages = []

    def send(self, message: OTPMessage) -> None:
        self.messages.append(message)


def test_otp_provider_is_abstract():
    with pytest.raises(TypeError):
        OTPProvider()  # type: ignore[abstract]


def test_otp_message_is_immutable():
    message = OTPMessage(phone="+998901234567", code="123456")

    with pytest.raises(FrozenInstanceError):
        message.code = "654321"  # type: ignore[misc]


def test_generate_otp_returns_six_digits():
    code = OTPService.generate_otp()

    assert len(code) == 6
    assert code.isdecimal()


def test_cache_lifecycle_and_attempts_are_bounded():
    cache = FakeCache()
    service = OTPService(cache_backend=cache, providers={})

    service.set_otp("+998901234567", "123456", ttl=30)
    assert service.get_otp("+998901234567") == "123456"
    assert service.pop_otp("+998901234567") == "123456"
    assert service.get_otp("+998901234567") is None

    attempts = 0
    for _ in range(OTP_ATTEMPT_LIMIT + 2):
        attempts = service.increment_otp_attempts("+998901234567")

    assert attempts == OTP_ATTEMPT_LIMIT
    assert service.get_otp_attempts("+998901234567") == OTP_ATTEMPT_LIMIT
    service.clear_otp_attempts("+998901234567")
    assert service.get_otp_attempts("+998901234567") == 0


def test_dispatch_sends_immutable_message_to_injected_provider():
    provider = RecordingProvider()
    service = OTPService(cache_backend=FakeCache(), providers={"future": provider})

    with override_settings(OTP_DEV_BYPASS_CODE=""):
        service.dispatch("+998901234567", "123456", "future")

    assert provider.messages == [OTPMessage(phone="+998901234567", code="123456")]


def test_dispatch_rejects_unknown_channel():
    service = OTPService(cache_backend=FakeCache(), providers={})

    with override_settings(OTP_DEV_BYPASS_CODE=""), pytest.raises(OTPDeliveryError):
        service.dispatch("+998901234567", "123456", "unknown")


def test_get_available_channels_reflects_settings():
    service = OTPService(cache_backend=FakeCache())

    with override_settings(OTP_TELEGRAM_ENABLED=True, OTP_SMS_ENABLED=True):
        assert service.get_available_channels() == ["telegram", "sms"]

    with override_settings(OTP_TELEGRAM_ENABLED=True, OTP_SMS_ENABLED=False):
        assert service.get_available_channels() == ["telegram"]

    with override_settings(OTP_TELEGRAM_ENABLED=False, OTP_SMS_ENABLED=True):
        assert service.get_available_channels() == ["sms"]

    with override_settings(OTP_TELEGRAM_ENABLED=False, OTP_SMS_ENABLED=False):
        assert service.get_available_channels() == []


def test_dispatch_rejects_disabled_channel():
    service = OTPService(cache_backend=FakeCache())

    with (
        override_settings(OTP_DEV_BYPASS_CODE="", OTP_TELEGRAM_ENABLED=False, OTP_SMS_ENABLED=True),
        pytest.raises(OTPDeliveryError),
    ):
        service.dispatch("+998901234567", "123456", "telegram")
