import json

import jwt
import pytest
from account.models import User
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart

from api.v1.mobile.auth import views
from tests.factories import UserFactory


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def _post(api_client, path, payload):
    return api_client.post(path, data=json.dumps(payload), content_type="application/json")


def _put(api_client, path, payload, **headers):
    return api_client.put(path, data=json.dumps(payload), content_type="application/json", **headers)


def _put_avatar(api_client, path, image, **headers):
    return api_client.put(
        path,
        data=encode_multipart(BOUNDARY, {"image": image}),
        content_type=MULTIPART_CONTENT,
        **headers,
    )


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


@pytest.mark.django_db
class TestMobileUserMeAPI:
    path = "/api/v1/mobile/account/me/"
    avatar_path = "/api/v1/mobile/account/me/avatar/"

    def test_get_returns_only_mobile_profile_fields(self, api_client, jwt_header, user):
        response = api_client.get(self.path, **jwt_header)

        assert response.status_code == 200
        assert response.json()["data"] == {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "patronymic": user.patronymic,
            "email": user.email,
            "phone": user.phone,
            "nationality": user.nationality,
            "avatar_url": None,
        }

    def test_get_requires_authentication(self, api_client):
        response = api_client.get(self.path)

        assert response.status_code == 401

    def test_raw_mobile_me_route_does_not_exist(self, api_client, jwt_header):
        response = api_client.get("/api/v1/mobile/me/", **jwt_header)

        assert response.status_code == 404

    def test_put_updates_editable_profile_fields(self, api_client, jwt_header, user):
        response = _put(
            api_client,
            self.path,
            {
                "first_name": "  Aziz ",
                "last_name": " Karimov ",
                "patronymic": " ",
                "email": "aziz@example.com",
                "nationality": " Uzbek ",
            },
            **jwt_header,
        )

        assert response.status_code == 200
        assert response.json()["data"] == {
            "id": user.id,
            "first_name": "Aziz",
            "last_name": "Karimov",
            "patronymic": None,
            "email": "aziz@example.com",
            "phone": user.phone,
            "nationality": "Uzbek",
            "avatar_url": None,
        }
        user.refresh_from_db()
        assert user.first_name == "Aziz"
        assert user.last_name == "Karimov"
        assert user.patronymic is None
        assert user.email == "aziz@example.com"
        assert user.nationality == "Uzbek"

    def test_put_rejects_invalid_fields(self, api_client, jwt_header):
        response = _put(
            api_client,
            self.path,
            {
                "first_name": "",
                "last_name": None,
                "patronymic": None,
                "email": "not-an-email",
                "nationality": None,
            },
            **jwt_header,
        )

        assert response.status_code == 400
        assert response.json()["success"] is False
        assert response.json()["message"] == "Validation error"

    def test_put_rejects_protected_fields(self, api_client, jwt_header):
        response = _put(
            api_client,
            self.path,
            {
                "first_name": "Aziz",
                "last_name": None,
                "patronymic": None,
                "email": "aziz@example.com",
                "nationality": None,
                "phone": "+998901111111",
            },
            **jwt_header,
        )

        assert response.status_code == 400
        assert response.json()["success"] is False
        assert response.json()["message"] == "Validation error"

    def test_put_rejects_an_email_used_by_another_user(self, api_client, jwt_header):
        taken_email = UserFactory().email
        response = _put(
            api_client,
            self.path,
            {
                "first_name": "Aziz",
                "last_name": None,
                "patronymic": None,
                "email": taken_email,
                "nationality": None,
            },
            **jwt_header,
        )

        assert response.status_code == 409
        assert response.json() == {
            "success": False,
            "message": "Data conflict",
            "error": "This email is already in use",
        }

    def test_avatar_upload_replaces_previous_file_and_returns_profile(self, api_client, jwt_header, user):
        first_response = _put_avatar(
            api_client,
            self.avatar_path,
            SimpleUploadedFile("first.png", b"first", content_type="image/png"),
            **jwt_header,
        )

        assert first_response.status_code == 200
        user.refresh_from_db()
        first_avatar_name = user.avatar.name
        assert default_storage.exists(first_avatar_name)
        assert first_response.json()["data"]["avatar_url"].endswith(f"/media/{first_avatar_name}")

        second_response = _put_avatar(
            api_client,
            self.avatar_path,
            SimpleUploadedFile("second.png", b"second", content_type="image/png"),
            **jwt_header,
        )

        assert second_response.status_code == 200
        user.refresh_from_db()
        assert user.avatar.name != first_avatar_name
        assert not default_storage.exists(first_avatar_name)
        assert default_storage.exists(user.avatar.name)
        assert second_response.json()["data"]["avatar_url"].endswith(f"/media/{user.avatar.name}")

    def test_avatar_delete_removes_file_and_returns_profile(self, api_client, jwt_header, user):
        user.avatar = SimpleUploadedFile("avatar.png", b"avatar", content_type="image/png")
        user.save(update_fields=["avatar"])
        avatar_name = user.avatar.name
        assert default_storage.exists(avatar_name)

        response = api_client.delete(self.avatar_path, **jwt_header)

        assert response.status_code == 200
        assert response.json()["data"]["avatar_url"] is None
        user.refresh_from_db()
        assert not user.avatar
        assert not default_storage.exists(avatar_name)

    def test_avatar_actions_require_authentication(self, api_client):
        upload_response = _put_avatar(
            api_client,
            self.avatar_path,
            SimpleUploadedFile("avatar.png", b"avatar", content_type="image/png"),
        )
        delete_response = api_client.delete(self.avatar_path)

        assert upload_response.status_code == 401
        assert delete_response.status_code == 401

    def test_avatar_upload_rejects_invalid_media(self, api_client, jwt_header):
        response = _put_avatar(
            api_client,
            self.avatar_path,
            SimpleUploadedFile("avatar.txt", b"not an image", content_type="text/plain"),
            **jwt_header,
        )

        assert response.status_code == 400
        assert response.json() == {
            "success": False,
            "message": "Upload failed",
            "error": "Unsupported image type 'text/plain'",
        }
