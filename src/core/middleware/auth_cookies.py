"""Deliver JWT tokens as httpOnly cookies instead of a JSON body.

On a successful login/refresh this middleware moves the access + refresh tokens
out of the response body and into httpOnly cookies (so JS never sees them), and
on logout it clears them. The API itself still returns the tokens in the body
(the views are unchanged); this middleware is the single place that translates
that into cookies + strips the raw values from the payload.
"""

import json
from http import HTTPStatus

from core.auth_cookies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    access_cookie_kwargs,
    refresh_cookie_kwargs,
)

LOGIN_PATHS = ("/api/v1/auth/login/", "/api/v1/auth/refresh/")
LOGOUT_PATH = "/api/v1/auth/logout/"


class AuthCookieMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path

        if path in LOGIN_PATHS and response.status_code == HTTPStatus.OK:
            self._set_token_cookies(request, response)
        elif path == LOGOUT_PATH and response.status_code == HTTPStatus.OK:
            response.delete_cookie(ACCESS_COOKIE, path="/")
            response.delete_cookie(REFRESH_COOKIE, path="/")

        return response

    def _should_strip_body_tokens(self, request) -> bool:
        # If client explicitly requested bearer transport or provided refresh_token
        # in the request body (e.g. mobile or API clients), preserve body tokens.
        if request.headers.get("X-Auth-Transport") == "bearer":
            return False
        if request.path == "/api/v1/auth/refresh/":
            body = self._read_request_json(request)
            if body and (body.get("refresh_token") or body.get("refresh")):
                return False
        return True

    def _set_token_cookies(self, request, response) -> None:
        payload = self._read_json(response)
        if payload is None:
            return
        data = payload.get("data")
        if not isinstance(data, dict):
            return
        access = data.get("access_token")
        refresh = data.get("refresh_token")
        if not access or not refresh:
            return

        response.set_cookie(ACCESS_COOKIE, access, **access_cookie_kwargs())
        response.set_cookie(REFRESH_COOKIE, refresh, **refresh_cookie_kwargs())

        if self._should_strip_body_tokens(request):
            # Strip the raw tokens from the body so browser scripts never read them.
            data["access_token"] = ""
            data["refresh_token"] = ""
            response.content = json.dumps(payload).encode()

    @staticmethod
    def _read_request_json(request):
        try:
            return json.loads(request.body)
        except ValueError, TypeError:
            return None

    @staticmethod
    def _read_json(response):
        content_type = response.get("Content-Type", "")
        if "application/json" not in content_type:
            return None
        try:
            return json.loads(response.content)
        except ValueError, TypeError:
            return None
