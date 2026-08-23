"""JWT authentication middleware for the chat WebSocket endpoint."""

from __future__ import annotations

from http.cookies import SimpleCookie

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


def _header_value(scope: dict, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _authenticate(scope: dict):
    """Use the same decode, user, and blacklist checks as HTTP controllers."""
    from core.api.permissions import BlacklistAwareJWTSyncAuth

    authorization = _header_value(scope, b"authorization")
    if not authorization:
        raw_cookie = _header_value(scope, b"cookie")
        if raw_cookie:
            cookies = SimpleCookie()
            cookies.load(raw_cookie)
            access_cookie = cookies.get("ideal_access")
            if access_cookie is not None:
                authorization = f"Bearer {access_cookie.value}"
    if not authorization:
        return AnonymousUser(), None

    auth = BlacklistAwareJWTSyncAuth()
    encoded = auth.split_encoded_token(authorization)
    if encoded is None:
        return AnonymousUser(), None
    try:
        token = auth.decode_token(encoded)
        user = auth.get_user(token)
        auth.check_auth(user, token)
    except Exception:  # Authentication failures never expose token details.
        return AnonymousUser(), None
    return user, token


class WebSocketJWTAuthMiddleware(BaseMiddleware):
    """Attach an authenticated user to the Channels scope."""

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        user, token = await database_sync_to_async(_authenticate)(scope)
        scope["user"] = user
        scope["chat_jwt"] = token
        return await super().__call__(scope, receive, send)
