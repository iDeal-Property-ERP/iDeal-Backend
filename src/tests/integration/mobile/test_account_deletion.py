import json

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile

from api.v1.mobile.account import views as account_views
from api.v1.mobile.auth import views as auth_views
from tests.factories import BookingFactory, DeviceTokenFactory, NotificationPreferenceFactory, TenantFactory


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def _post(api_client, path, payload, **headers):
    return api_client.post(path, data=json.dumps(payload), content_type="application/json", **headers)


@pytest.mark.django_db
def test_deletion_anonymizes_user_preserves_history_and_allows_fresh_phone_signup(api_client, monkeypatch):
    user = TenantFactory(phone="+998901234567", first_name="Delete", last_name="Me")
    booking = BookingFactory(tenant=user)
    DeviceTokenFactory(user=user)
    NotificationPreferenceFactory(user=user)
    user.avatar.save("avatar.png", SimpleUploadedFile("avatar.png", b"image data", content_type="image/png"))
    monkeypatch.setattr(settings, "OTP_DEV_BYPASS_CODE", "123456")
    monkeypatch.setattr(auth_views.otp_service, "generate_otp", lambda: "999999")
    monkeypatch.setattr(account_views.otp_service, "generate_otp", lambda: "999999")

    login_request = _post(
        api_client,
        "/api/v1/mobile/auth/otp/request/",
        {"phone": user.phone, "channel": "telegram"},
    )
    assert login_request.status_code == 200
    login_response = _post(
        api_client,
        "/api/v1/mobile/auth/otp/verify/",
        {"phone": user.phone, "code": "123456"},
    )
    access_token = login_response.json()["data"]["access_token"]
    header = {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}

    otp_response = _post(
        api_client,
        "/api/v1/mobile/account/deletion/otp/request/",
        {"channel": "telegram"},
        **header,
    )
    assert otp_response.status_code == 200
    assert otp_response.json()["data"]["expires_in"] == 300

    deletion_response = _post(
        api_client,
        "/api/v1/mobile/account/deletion/confirm/",
        {"code": "123456"},
        **header,
    )
    assert deletion_response.status_code == 200
    assert deletion_response.json()["data"] == {"deleted": True}

    from account.models import User
    from notification.models import DeviceToken, NotificationPreference

    deleted_user = User.global_objects.get(pk=user.pk)
    assert deleted_user.is_deleted is True
    assert deleted_user.is_active is False
    assert deleted_user.phone is None
    assert deleted_user.email.endswith("@deleted.ideal.local")
    assert deleted_user.first_name == "Deleted user"
    assert not deleted_user.has_usable_password()
    assert not deleted_user.avatar
    assert DeviceToken.global_objects.filter(user_id=user.pk).count() == 0
    assert NotificationPreference.global_objects.filter(user_id=user.pk).count() == 0
    assert booking.__class__.objects.get(pk=booking.pk).tenant_id == user.pk

    assert api_client.get("/api/v1/mobile/account/me/", **header).status_code == 401

    assert (
        _post(
            api_client,
            "/api/v1/mobile/auth/otp/request/",
            {"phone": "+998901234567", "channel": "telegram"},
        ).status_code
        == 200
    )
    fresh_login = _post(
        api_client,
        "/api/v1/mobile/auth/otp/verify/",
        {"phone": "+998901234567", "code": "123456"},
    )
    assert fresh_login.status_code == 200
    fresh_user = User.objects.get(phone="+998901234567")
    assert fresh_user.pk != user.pk
    assert fresh_user.first_name == ""
    assert fresh_user.bookings.count() == 0


@pytest.mark.django_db
def test_deletion_code_is_purpose_scoped(api_client, monkeypatch):
    user = TenantFactory(phone="+998901234568")
    monkeypatch.setattr(settings, "OTP_DEV_BYPASS_CODE", "999999")
    monkeypatch.setattr(auth_views.otp_service, "generate_otp", lambda: "111111")
    monkeypatch.setattr(account_views.otp_service, "generate_otp", lambda: "222222")

    assert (
        _post(
            api_client,
            "/api/v1/mobile/auth/otp/request/",
            {"phone": user.phone, "channel": "telegram"},
        ).status_code
        == 200
    )
    login_response = _post(
        api_client,
        "/api/v1/mobile/auth/otp/verify/",
        {"phone": user.phone, "code": "111111"},
    )
    header = {"HTTP_AUTHORIZATION": f"Bearer {login_response.json()['data']['access_token']}"}

    assert (
        _post(
            api_client,
            "/api/v1/mobile/account/deletion/otp/request/",
            {"channel": "telegram"},
            **header,
        ).status_code
        == 200
    )
    response = _post(
        api_client,
        "/api/v1/mobile/account/deletion/confirm/",
        {"code": "111111"},
        **header,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Invalid or expired code"


@pytest.mark.django_db
def test_deletion_code_expiry_and_attempt_limit(api_client, monkeypatch):
    user = TenantFactory(phone="+998901234569")
    monkeypatch.setattr(settings, "OTP_DEV_BYPASS_CODE", "999999")
    monkeypatch.setattr(account_views.otp_service, "generate_otp", lambda: "222222")
    login_response = _post(
        api_client,
        "/api/v1/mobile/auth/otp/verify/",
        {"phone": user.phone, "code": "999999"},
    )
    header = {"HTTP_AUTHORIZATION": f"Bearer {login_response.json()['data']['access_token']}"}

    assert (
        _post(
            api_client,
            "/api/v1/mobile/account/deletion/otp/request/",
            {"channel": "telegram"},
            **header,
        ).status_code
        == 200
    )
    account_views.otp_service.pop_otp(user.phone, purpose=account_views.ACCOUNT_DELETION_OTP_PURPOSE)
    expired = _post(
        api_client,
        "/api/v1/mobile/account/deletion/confirm/",
        {"code": "222222"},
        **header,
    )
    assert expired.status_code == 400

    assert (
        _post(
            api_client,
            "/api/v1/mobile/account/deletion/otp/request/",
            {"channel": "telegram"},
            **header,
        ).status_code
        == 200
    )
    for _ in range(5):
        invalid = _post(
            api_client,
            "/api/v1/mobile/account/deletion/confirm/",
            {"code": "000000"},
            **header,
        )
        assert invalid.status_code == 400

    locked = _post(
        api_client,
        "/api/v1/mobile/account/deletion/confirm/",
        {"code": "222222"},
        **header,
    )
    assert locked.status_code == 429
    assert locked.json()["error"] == "Too many verification attempts"
