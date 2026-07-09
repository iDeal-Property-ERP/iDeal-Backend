"""Cookie names + attributes for JWT auth delivered via httpOnly cookies.

The browser talks to the app origin (Next), which proxies to this API; login/
refresh responses set these cookies so the token never reaches JS, and the auth
layer reads the access token from the cookie when no Authorization header is sent.
"""

from django.conf import settings

ACCESS_COOKIE = "ideal_access"
REFRESH_COOKIE = "ideal_refresh"


def access_cookie_kwargs() -> dict:
    return _cookie_kwargs(settings.JWT_SETTINGS["ACCESS_TOKEN_LIFETIME"])


def refresh_cookie_kwargs() -> dict:
    return _cookie_kwargs(settings.JWT_SETTINGS["REFRESH_TOKEN_LIFETIME"])


def _cookie_kwargs(lifetime) -> dict:
    return {
        "max_age": int(lifetime.total_seconds()),
        "httponly": True,
        "secure": getattr(settings, "AUTH_COOKIE_SECURE", not settings.DEBUG),
        "samesite": "Lax",
        "path": "/",
        # No Domain: host-only, so the cookie binds to the app origin that served
        # the (proxied) response and the Next middleware can read it.
    }
