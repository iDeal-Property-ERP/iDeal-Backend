import pytest
import requests
from account.services.auth.otp import OTPDeliveryError
from account.services.auth.providers.base import OTPMessage, OTPMessagePurpose
from account.services.auth.providers.eskiz import ESKIZ_TOKEN_CACHE_KEY, SMS_TEXT_TEMPLATES, EskizGateway
from account.services.auth.providers.telegram import TelegramGateway
from django.test import override_settings


class FakeCache:
    def __init__(self):
        self.values = {}

    def set(self, key, value, timeout=None):
        self.values[key] = value

    def get(self, key, default=None):
        return self.values.get(key, default)

    def delete(self, key):
        return self.values.pop(key, None)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeHTTPClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_telegram_sends_gateway_payload():
    http = FakeHTTPClient(FakeResponse(200, {"ok": True}))
    gateway = TelegramGateway(http_client=http)

    with override_settings(TELEGRAM_GATEWAY_TOKEN="telegram-token"):
        gateway.send(OTPMessage(phone="+998901234567", code="123456"))

    url, kwargs = http.calls[0]
    assert url == "https://gatewayapi.telegram.org/sendVerificationMessage"
    assert kwargs["headers"] == {"Authorization": "Bearer telegram-token"}
    assert kwargs["json"] == {"phone_number": "+998901234567", "code": "123456"}


@pytest.mark.parametrize("response", [FakeResponse(200, []), FakeResponse(500, {"ok": False})])
def test_telegram_rejects_malformed_or_failed_response(response):
    gateway = TelegramGateway(http_client=FakeHTTPClient(response))

    with override_settings(TELEGRAM_GATEWAY_TOKEN="telegram-token"), pytest.raises(OTPDeliveryError):
        gateway.send(OTPMessage(phone="+998901234567", code="123456"))


def test_provider_network_error_is_normalized():
    gateway = TelegramGateway(http_client=FakeHTTPClient(requests.RequestException("offline")))

    with override_settings(TELEGRAM_GATEWAY_TOKEN="telegram-token"), pytest.raises(OTPDeliveryError):
        gateway.send(OTPMessage(phone="+998901234567", code="123456"))


@pytest.mark.parametrize(
    ("purpose", "expected_text"),
    [
        (OTPMessagePurpose.LOGIN, "iDeal ilovasiga kirish uchun tasdiqlash kodi: 123456"),
        (
            OTPMessagePurpose.PHONE_CHANGE,
            "iDeal ilovasida telefon raqamingizni o‘zgartirish uchun tasdiqlash kodi: 123456",
        ),
        (
            OTPMessagePurpose.ACCOUNT_DELETION,
            "iDeal ilovasidagi akkauntingizni o‘chirish uchun tasdiqlash kodi: 123456",
        ),
    ],
)
def test_eskiz_uses_moderation_ready_text_for_each_purpose(purpose, expected_text):
    cache = FakeCache()
    cache.set(ESKIZ_TOKEN_CACHE_KEY, "cached-token")
    http = FakeHTTPClient(FakeResponse(200, {"success": True}))
    gateway = EskizGateway(cache_backend=cache, http_client=http)

    with override_settings(
        ESKIZ_EMAIL="email@example.com",
        ESKIZ_PASSWORD="password",
        ESKIZ_BASE_URL="https://eskiz.example/api",
        ESKIZ_FROM="4546",
    ):
        gateway.send(OTPMessage(phone="+998901234567", code="123456", purpose=purpose))

    assert len(http.calls) == 1
    assert http.calls[0][1]["headers"] == {"Authorization": "Bearer cached-token"}
    assert http.calls[0][1]["data"]["message"] == expected_text


def test_eskiz_sms_text_templates_cover_every_otp_message_purpose():
    assert set(SMS_TEXT_TEMPLATES) == set(OTPMessagePurpose)


def test_eskiz_refreshes_token_once_after_unauthorized_message():
    http = FakeHTTPClient(
        FakeResponse(200, {"data": {"token": "old-token"}}),
        FakeResponse(401, {"ok": False}),
        FakeResponse(200, {"data": {"token": "new-token"}}),
        FakeResponse(200, {"success": True}),
    )
    cache = FakeCache()
    gateway = EskizGateway(cache_backend=cache, http_client=http)

    with override_settings(
        ESKIZ_EMAIL="email@example.com",
        ESKIZ_PASSWORD="password",
        ESKIZ_BASE_URL="https://eskiz.example/api",
        ESKIZ_FROM="4546",
    ):
        gateway.send(OTPMessage(phone="+998901234567", code="123456"))

    assert cache.get(ESKIZ_TOKEN_CACHE_KEY) == "new-token"
    assert http.calls[1][1]["headers"] == {"Authorization": "Bearer old-token"}
    assert http.calls[3][1]["headers"] == {"Authorization": "Bearer new-token"}
