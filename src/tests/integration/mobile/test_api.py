import json

import jwt
import pytest
from account.models import User
from django.conf import settings
from django.core.cache import cache

from api.v1.mobile.auth import views
from tests.factories import UserFactory


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def _post(api_client, path, payload):
    return api_client.post(path, data=json.dumps(payload), content_type="application/json")


def _request_otp(api_client, phone="+998901234567"):
    return _post(
        api_client,
        "/api/v1/mobile/auth/otp/request/",
        {"phone": phone, "channel": "telegram"},
    )


def _verify_otp(api_client, phone="+998901234567", code="123456"):
    return _post(
        api_client,
        "/api/v1/mobile/auth/otp/verify/",
        {"phone": phone, "code": code},
    )


@pytest.mark.django_db
def test_request_and_verify_provisions_user_and_returns_valid_jwt(api_client, monkeypatch):
    monkeypatch.setattr(settings, "OTP_DEV_BYPASS_CODE", "123456")
    monkeypatch.setattr(views.otp_service, "generate_otp", lambda: "999999")

    request_response = _request_otp(api_client)
    assert request_response.status_code == 200
    assert request_response.json() == {
        "success": True,
        "message": "OK",
        "data": {"channel": "telegram", "expires_in": 300, "resend_after": 60},
    }

    verify_response = _verify_otp(api_client)
    assert verify_response.status_code == 200
    tokens = verify_response.json()["data"]
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    user = User.objects.get(phone="+998901234567")
    assert user.is_verified is True
    assert user.has_usable_password() is False

    payload = jwt.decode(tokens["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert payload["sub"] == str(user.pk)
    assert payload["extras"]["role"] == user.role
    assert payload["extras"]["must_change_password"] == user.must_change_password

    authenticated_response = api_client.get(
        "/api/v1/users/me/",
        HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
    )
    assert authenticated_response.status_code == 200
    assert authenticated_response.json()["data"]["phone"] == "+998901234567"


def test_invalid_code_is_rejected(api_client, monkeypatch):
    monkeypatch.setattr(settings, "OTP_DEV_BYPASS_CODE", "123456")
    monkeypatch.setattr(views.otp_service, "generate_otp", lambda: "999999")

    assert _request_otp(api_client).status_code == 200
    response = _verify_otp(api_client, code="000000")

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "Invalid or expired code"


def test_invalid_phone_is_rejected(api_client, monkeypatch):
    monkeypatch.setattr(settings, "OTP_DEV_BYPASS_CODE", "123456")

    response = _post(
        api_client,
        "/api/v1/mobile/auth/otp/request/",
        {"phone": "901234567", "channel": "telegram"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "Invalid phone number"


def test_verification_attempts_are_capped(api_client, monkeypatch):
    monkeypatch.setattr(settings, "OTP_DEV_BYPASS_CODE", "123456")
    monkeypatch.setattr(views.otp_service, "generate_otp", lambda: "999999")

    assert _request_otp(api_client).status_code == 200
    for _ in range(5):
        response = _verify_otp(api_client, code="000000")
        assert response.status_code == 400

    capped_response = _verify_otp(api_client, code="123456")
    assert capped_response.status_code == 429
    assert capped_response.json()["success"] is False


def test_otp_request_is_rate_limited(api_client, monkeypatch):
    monkeypatch.setattr(settings, "OTP_DEV_BYPASS_CODE", "123456")
    monkeypatch.setattr(views.otp_service, "generate_otp", lambda: "999999")

    for index in range(3):
        response = _request_otp(api_client, phone=f"+9989012345{index:02d}")
        assert response.status_code == 200

    limited_response = _request_otp(api_client, phone="+998901234599")
    assert limited_response.status_code == 429
    assert limited_response.json()["success"] is False


@pytest.mark.django_db
def test_existing_phone_user_is_reused_and_token_authenticates(api_client, monkeypatch):
    phone = "+998901234568"
    user = UserFactory(phone=phone)
    monkeypatch.setattr(settings, "OTP_DEV_BYPASS_CODE", "123456")
    monkeypatch.setattr(views.otp_service, "generate_otp", lambda: "999999")

    assert _request_otp(api_client, phone=phone).status_code == 200
    response = _verify_otp(api_client, phone=phone)
    assert response.status_code == 200

    tokens = response.json()["data"]
    assert User.objects.filter(phone=phone).count() == 1
    assert User.objects.get(phone=phone).pk == user.pk

    authenticated_response = api_client.get(
        "/api/v1/users/me/",
        HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
    )
    assert authenticated_response.status_code == 200
    assert authenticated_response.json()["data"]["id"] == user.pk
