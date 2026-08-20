import uuid
from http import HTTPStatus

from account.models import User
from account.services.auth.otp import (
    OTP_ATTEMPT_LIMIT,
    OTPDeliveryError,
    OTPService,
)
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dmr import Body
from dmr.security.jwt.auth import set_request_attrs
from dmr.security.jwt.token import JWToken

from api.v1.mobile.auth.schemas import OTPMethodsOutput, OTPRequestInput, OTPVerifyInput
from core.api.mixins import JWTMixin
from core.api.views import BaseController
from core.constants import UserRole
from core.utils.phone import normalize_uzbekistan_phone
from core.utils.rate_limit import rate_limit

otp_service = OTPService()


def normalize_phone(phone: str) -> str:
    """Backward-compatible mobile auth alias for the shared phone validator."""
    return normalize_uzbekistan_phone(phone)


def _invalid_phone(controller: BaseController):
    return controller.fail(
        error=str(_("Invalid phone number")),
        message=str(_("Validation error")),
        status_code=HTTPStatus.BAD_REQUEST,
    )


def _get_or_create_phone_user(phone: str) -> User:
    user = User.objects.filter(phone=phone).first()
    if user is not None:
        return user

    user = User.objects.create(
        username=uuid.uuid4().hex[:30],
        email=None,
        first_name="",
        phone=phone,
        role=UserRole.TENANT,
        is_verified=True,
    )
    user.set_unusable_password()
    user.save(update_fields=["password"])
    return user


class OTPMethodsView(BaseController):
    auth = ()

    def get(self) -> dict:
        channels = otp_service.get_available_channels()
        return self.ok(OTPMethodsOutput(channels=channels).model_dump(mode="json"))


class OTPRequestView(BaseController):
    auth = ()

    @rate_limit(requests=3, window_seconds=3600)
    def post(self, parsed_body: Body[OTPRequestInput]) -> dict:
        try:
            phone = normalize_phone(parsed_body.phone)
        except ValueError:
            return _invalid_phone(self)

        if parsed_body.channel not in otp_service.get_available_channels():
            return self.fail(
                error=str(_("Selected OTP channel is disabled or unavailable")),
                message=str(_("Validation error")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        code = otp_service.generate_otp()
        otp_service.clear_otp_attempts(phone)
        otp_service.set_otp(phone, code)
        try:
            otp_service.dispatch(phone, code, parsed_body.channel)
        except OTPDeliveryError:
            otp_service.pop_otp(phone)
            return self.fail(
                error=str(_("Unable to deliver verification code")),
                message=str(_("Please try again later")),
                status_code=HTTPStatus.BAD_GATEWAY,
            )

        return self.ok(
            {
                "channel": parsed_body.channel,
                "expires_in": 300,
                "resend_after": 60,
            },
            status_code=HTTPStatus.OK,
        )


class OTPVerifyView(JWTMixin, BaseController):
    auth = ()
    jwt_token_cls = JWToken
    jwt_audiences = None

    @staticmethod
    def make_jwt_id() -> str:
        return uuid.uuid4().hex

    def make_api_response(self) -> dict[str, str]:
        return {
            "access_token": self.create_jwt_token(
                token_type="access",
                expiration=timezone.now() + self.jwt_expiration,
            ),
            "refresh_token": self.create_jwt_token(
                token_type="refresh",
                expiration=timezone.now() + self.jwt_refresh_expiration,
            ),
        }

    def post(self, parsed_body: Body[OTPVerifyInput]) -> dict:
        try:
            phone = normalize_phone(parsed_body.phone)
        except ValueError:
            return _invalid_phone(self)

        if otp_service.get_otp_attempts(phone) >= OTP_ATTEMPT_LIMIT:
            return self.fail(
                error=str(_("Too many verification attempts")),
                message=str(_("Please request a new code")),
                status_code=HTTPStatus.TOO_MANY_REQUESTS,
            )

        code = parsed_body.code.strip()
        bypass_code = settings.OTP_DEV_BYPASS_CODE
        if not ((bypass_code and code == bypass_code) or code == otp_service.get_otp(phone)):
            otp_service.increment_otp_attempts(phone)
            return self.fail(
                error=str(_("Invalid or expired code")),
                message=str(_("Verification failed")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        otp_service.pop_otp(phone)
        otp_service.clear_otp_attempts(phone)
        user = _get_or_create_phone_user(phone)
        set_request_attrs(self.request, user)
        return self.ok(self.make_api_response(), status_code=HTTPStatus.OK)
