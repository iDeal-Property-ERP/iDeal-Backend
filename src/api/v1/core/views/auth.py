from datetime import UTC, datetime
from http import HTTPStatus

import jwt
import pydantic
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dmr import Body, modify
from dmr.plugins.pydantic import PydanticFastSerializer
from dmr.security.jwt.auth import request_jwt
from dmr.security.jwt.views import (
    ObtainTokensPayload,
    ObtainTokensResponse,
    ObtainTokensSyncController,
    RefreshTokenSyncController,
)

from core.api.mixins import JWTMixin
from core.api.views import BaseController


def _decode_jti_exp(encoded_token: str) -> tuple[str | None, datetime | None]:
    """Extract (jti, expiry) from a token, ignoring expiry so a just-expired
    token can still be revoked. Returns (None, None) if it can't be decoded."""
    try:
        payload = jwt.decode(
            encoded_token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError:
        return None, None
    exp = payload.get("exp")
    exp_dt = datetime.fromtimestamp(exp, tz=UTC) if exp else None
    return payload.get("jti"), exp_dt


def _blacklist(jti: str | None, expires_at: datetime | None) -> None:
    if not jti:
        return
    from account.models import TokenBlacklist

    TokenBlacklist.objects.get_or_create(jti=jti, defaults={"expires_at": expires_at})


class LoginAPIView(
    JWTMixin, ObtainTokensSyncController[PydanticFastSerializer, ObtainTokensPayload, ObtainTokensResponse]
):
    def convert_auth_payload(self, payload: ObtainTokensPayload) -> ObtainTokensPayload:
        return {
            "username": payload["username"],
            "password": payload["password"],
        }

    def make_api_response(self) -> ObtainTokensResponse:
        return {
            # Short-lived access token (was defaulting to the 30-day lifetime).
            "access_token": self.create_jwt_token(
                token_type="access",
                expiration=timezone.now() + self.jwt_expiration,
            ),
            "refresh_token": self.create_jwt_token(
                token_type="refresh",
                expiration=timezone.now() + self.jwt_refresh_expiration,
            ),
        }

    @modify(status_code=HTTPStatus.OK)
    def post(self, parsed_body: Body[ObtainTokensPayload]) -> dict:
        return BaseController.ok(self.login(parsed_body))


class RefreshInput(pydantic.BaseModel):
    # All optional so a cookie-only refresh (empty body) passes validation; the
    # token is then read from the ``ideal_refresh`` cookie.
    refresh_token: str | None = None
    refresh: str | None = None


class RefreshAPIView(JWTMixin, RefreshTokenSyncController[PydanticFastSerializer, dict, ObtainTokensResponse]):
    def convert_refresh_payload(self, payload: dict) -> str:
        from core.auth_cookies import REFRESH_COOKIE

        return (
            payload.get("refresh")
            or payload.get("refresh_token")
            or self.request.COOKIES.get(REFRESH_COOKIE)
            or ""
        )

    def make_api_response(self) -> ObtainTokensResponse:
        return {
            "access_token": self.create_jwt_token(token_type="access", expiration=timezone.now() + self.jwt_expiration),
            "refresh_token": self.create_jwt_token(
                token_type="refresh",
                expiration=timezone.now() + self.jwt_refresh_expiration,
            ),
        }

    @modify(status_code=HTTPStatus.OK)
    def post(self, parsed_body: Body[RefreshInput]) -> dict:
        # Rotation + reuse detection: reject an already-consumed refresh token,
        # then revoke the presented one so it can't be replayed.
        body = parsed_body.model_dump()
        raw = self.convert_refresh_payload(body)
        if not raw:
            return BaseController.fail(
                error=str(_("Refresh token is required")),
                message=str(_("Validation error")),
            )
        jti, exp = _decode_jti_exp(raw)
        if jti:
            from account.models import TokenBlacklist

            if TokenBlacklist.objects.filter(jti=jti).exists():
                BaseController.fail(
                    error=str(_("Refresh token has been revoked")),
                    message=str(_("Token is invalid")),
                    status_code=HTTPStatus.UNAUTHORIZED,
                )
        response = self.refresh(body)
        _blacklist(jti, exp)
        return BaseController.ok(response)


class LogoutInput(pydantic.BaseModel):
    refresh_token: str | None = None


class LogoutAPIView(BaseController):
    def post(self, parsed_body: Body[LogoutInput]) -> dict:
        # Revoke the current access token (from the Authorization header) and the
        # supplied refresh token so the session cannot be resumed after logout.
        token = request_jwt(self.request)
        if token is not None and getattr(token, "jti", None):
            exp = getattr(token, "exp", None)
            exp_dt = exp if isinstance(exp, datetime) else None
            _blacklist(token.jti, exp_dt)
        from core.auth_cookies import REFRESH_COOKIE

        refresh_token = parsed_body.refresh_token or self.request.COOKIES.get(REFRESH_COOKIE)
        if refresh_token:
            _blacklist(*_decode_jti_exp(refresh_token))
        return self.ok(str(_("Logged out")), status_code=HTTPStatus.OK)


class SetPasswordInput(pydantic.BaseModel):
    current_password: str
    new_password: str = pydantic.Field(min_length=8)


class SetPasswordAPIView(BaseController):
    def post(self, parsed_body: Body[SetPasswordInput]) -> dict:
        user = self.request.user
        if not user.check_password(parsed_body.current_password):
            return self.fail(
                error=str(_("Current password is incorrect")),
                message=str(_("Invalid credentials")),
                status_code=HTTPStatus.BAD_REQUEST,
            )
        user.set_password(parsed_body.new_password)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])
        return self.ok(str(_("Password updated")), status_code=HTTPStatus.OK)


class TokenVerifyInput(pydantic.BaseModel):
    token: str


class TokenVerifyController(BaseController):
    auth = ()

    def post(self, parsed_body: Body[TokenVerifyInput]) -> dict:
        try:
            jwt.decode(parsed_body.token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return self.fail(str(_("Token is invalid")), status_code=HTTPStatus.UNAUTHORIZED)
        return self.ok(str(_("Token is valid")), status_code=HTTPStatus.OK)
