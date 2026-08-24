from http import HTTPStatus

from account.models import User
from account.services.auth.otp import OTP_ATTEMPT_LIMIT, OTPDeliveryError, OTPService
from account.services.deletion import AccountDeletionService
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from dmr import Body

from core.api.views import BaseController
from core.utils.phone import normalize_uzbekistan_phone
from core.utils.rate_limit import rate_limit

from .schemas import (
    PublicAccountDeletionChannelsOutput,
    PublicAccountDeletionConfirmInput,
    PublicAccountDeletionOTPRequestInput,
    UserMeOutput,
)

PUBLIC_ACCOUNT_DELETION_OTP_PURPOSE = "public-account-deletion"
otp_service = OTPService()


def _invalid_phone(controller: BaseController):
    return controller.fail(
        error=str(_("Invalid phone number")),
        message=str(_("Validation error")),
        status_code=HTTPStatus.BAD_REQUEST,
    )


class UserMeView(BaseController):
    def get(self) -> dict:
        user = getattr(self.request, "user", None)
        return self.ok(UserMeOutput.model_validate(user).model_dump(mode="json"))


class PublicAccountDeletionChannelsView(BaseController):
    auth = ()

    def get(self) -> dict:
        channels = otp_service.get_available_channels()
        return self.ok(PublicAccountDeletionChannelsOutput(channels=channels).model_dump(mode="json"))


class PublicAccountDeletionOTPRequestView(BaseController):
    auth = ()

    @rate_limit(requests=3, window_seconds=3600)
    def post(self, parsed_body: Body[PublicAccountDeletionOTPRequestInput]) -> dict:
        try:
            phone = normalize_uzbekistan_phone(parsed_body.phone)
        except ValueError:
            return _invalid_phone(self)

        user = User.objects.filter(phone=phone, is_active=True).first()
        if user is None:
            return self.fail(
                error=str(_("No active account found with this phone number")),
                message=str(_("Account not found")),
                status_code=HTTPStatus.NOT_FOUND,
            )

        if parsed_body.channel not in otp_service.get_available_channels():
            return self.fail(
                error=str(_("Selected OTP channel is disabled or unavailable")),
                message=str(_("Validation error")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        code = otp_service.generate_otp()
        otp_service.clear_otp_attempts(phone, purpose=PUBLIC_ACCOUNT_DELETION_OTP_PURPOSE)
        otp_service.set_otp(phone, code, purpose=PUBLIC_ACCOUNT_DELETION_OTP_PURPOSE)
        try:
            otp_service.dispatch(phone, code, parsed_body.channel)
        except OTPDeliveryError:
            otp_service.pop_otp(phone, purpose=PUBLIC_ACCOUNT_DELETION_OTP_PURPOSE)
            return self.fail(
                error=str(_("Unable to deliver verification code")),
                message=str(_("Please try again later")),
                status_code=HTTPStatus.BAD_GATEWAY,
            )

        return self.ok(
            {"channel": parsed_body.channel, "expires_in": 300, "resend_after": 60},
            status_code=HTTPStatus.OK,
        )


class PublicAccountDeletionConfirmView(BaseController):
    auth = ()

    @rate_limit(requests=10, window_seconds=3600)
    def post(self, parsed_body: Body[PublicAccountDeletionConfirmInput]) -> dict:
        try:
            phone = normalize_uzbekistan_phone(parsed_body.phone)
        except ValueError:
            return _invalid_phone(self)

        if otp_service.get_otp_attempts(phone, purpose=PUBLIC_ACCOUNT_DELETION_OTP_PURPOSE) >= OTP_ATTEMPT_LIMIT:
            return self.fail(
                error=str(_("Too many verification attempts")),
                message=str(_("Please request a new code")),
                status_code=HTTPStatus.TOO_MANY_REQUESTS,
            )

        code = parsed_body.code.strip()
        bypass_code = settings.OTP_DEV_BYPASS_CODE
        if not (
            (bypass_code and code == bypass_code)
            or code == otp_service.get_otp(phone, purpose=PUBLIC_ACCOUNT_DELETION_OTP_PURPOSE)
        ):
            otp_service.increment_otp_attempts(phone, purpose=PUBLIC_ACCOUNT_DELETION_OTP_PURPOSE)
            return self.fail(
                error=str(_("Invalid or expired code")),
                message=str(_("Verification failed")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        otp_service.pop_otp(phone, purpose=PUBLIC_ACCOUNT_DELETION_OTP_PURPOSE)
        otp_service.clear_otp_attempts(phone, purpose=PUBLIC_ACCOUNT_DELETION_OTP_PURPOSE)

        user = User.objects.filter(phone=phone, is_active=True).first()
        if user is None:
            return self.fail(
                error=str(_("No active account found with this phone number")),
                message=str(_("Account not found")),
                status_code=HTTPStatus.NOT_FOUND,
            )

        AccountDeletionService.delete_account(user)
        return self.ok({"deleted": True}, status_code=HTTPStatus.OK)
