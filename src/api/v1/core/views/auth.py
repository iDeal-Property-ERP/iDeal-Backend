import jwt
import pydantic
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dmr import Body
from dmr.plugins.pydantic import PydanticFastSerializer
from dmr.security.jwt.views import (
    ObtainTokensPayload,
    ObtainTokensResponse,
    ObtainTokensSyncController,
    RefreshTokenSyncController,
)

from core.api.mixins import JWTMixin
from core.api.views import BaseController


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
            "access_token": self.create_jwt_token(token_type="access"),
            "refresh_token": self.create_jwt_token(
                token_type="refresh",
                expiration=timezone.now() + self.jwt_expiration,
            ),
        }


class RefreshAPIView(JWTMixin, RefreshTokenSyncController[PydanticFastSerializer, dict, ObtainTokensResponse]):
    def convert_refresh_payload(self, payload: dict) -> str:
        refresh_token = payload.get("refresh") or payload.get("refresh_token") or ""
        return refresh_token

    def make_api_response(self) -> ObtainTokensResponse:
        return {
            "access_token": self.create_jwt_token(token_type="access"),
            "refresh_token": self.create_jwt_token(
                token_type="refresh",
                expiration=timezone.now() + self.jwt_refresh_expiration,
            ),
        }


class TokenVerifyInput(pydantic.BaseModel):
    token: str


class TokenVerifyController(BaseController):
    auth = ()

    def post(self, parsed_body: Body[TokenVerifyInput]) -> dict:
        try:
            jwt.decode(parsed_body.token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return self.fail(str(_("Token is invalid")))
        return self.ok(str(_("Token is valid")))
