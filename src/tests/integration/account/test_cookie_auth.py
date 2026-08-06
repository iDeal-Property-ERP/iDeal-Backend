"""httpOnly-cookie JWT delivery (M-15): login sets cookies + strips the body,
the access token carries the role claim, cookie-only requests authenticate, and
refresh/logout read/clear the cookies."""

import base64
import json

import pytest

from core.auth_cookies import ACCESS_COOKIE, REFRESH_COOKIE
from tests.factories import UserFactory

PASSWORD = "testpass123"


@pytest.fixture
def account():
    user = UserFactory()
    user.set_password(PASSWORD)
    user.save()
    return user


def _login(api_client, user):
    return api_client.post(
        "/api/v1/auth/login/",
        data=json.dumps({"username": user.username, "password": PASSWORD}),
        content_type="application/json",
    )


def _decode_extras(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload)).get("extras", {})


@pytest.mark.django_db
class TestCookieAuth:
    def test_login_sets_httponly_cookies_and_strips_body(self, api_client, account):
        response = _login(api_client, account)
        assert response.status_code == 200

        assert ACCESS_COOKIE in response.cookies
        assert REFRESH_COOKIE in response.cookies
        assert response.cookies[ACCESS_COOKIE]["httponly"] is True
        assert response.cookies[REFRESH_COOKIE]["httponly"] is True
        assert response.cookies[ACCESS_COOKIE]["samesite"] == "Lax"

        # Raw tokens must not leak in the body.
        data = response.json()["data"]
        assert data["access_token"] == ""
        assert data["refresh_token"] == ""

    def test_access_token_carries_role_claim(self, api_client, account):
        response = _login(api_client, account)
        extras = _decode_extras(response.cookies[ACCESS_COOKIE].value)
        assert extras["role"] == account.role
        assert extras["must_change_password"] == account.must_change_password

    def test_cookie_only_request_authenticates(self, api_client, account):
        _login(api_client, account)  # client now holds the cookies
        # No Authorization header — auth must come from the cookie.
        response = api_client.get("/api/v1/users/me/")
        assert response.status_code == 200
        assert response.json()["data"]["username"] == account.username

    def test_refresh_reads_refresh_cookie(self, api_client, account):
        _login(api_client, account)
        response = api_client.post(
            "/api/v1/auth/refresh/", data=json.dumps({}), content_type="application/json"
        )
        assert response.status_code == 200
        assert ACCESS_COOKIE in response.cookies
        # Rotated access token still carries the role claim.
        assert _decode_extras(response.cookies[ACCESS_COOKIE].value)["role"] == account.role

    def test_logout_clears_cookies_and_revokes(self, api_client, account):
        _login(api_client, account)
        response = api_client.post(
            "/api/v1/auth/logout/", data=json.dumps({}), content_type="application/json"
        )
        assert response.status_code == 200
        # delete_cookie empties the value.
        assert response.cookies[ACCESS_COOKIE].value == ""
        assert response.cookies[REFRESH_COOKIE].value == ""
        # Session can no longer be used.
        assert api_client.get("/api/v1/users/me/").status_code == 401
