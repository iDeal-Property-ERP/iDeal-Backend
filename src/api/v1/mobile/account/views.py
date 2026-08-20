from http import HTTPStatus
from io import BytesIO

from account.models import TokenBlacklist, User
from account.services.auth.otp import OTP_ATTEMPT_LIMIT, OTPDeliveryError, OTPService
from account.services.deletion import AccountDeletionService
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from dmr import Body
from dmr.security.jwt.auth import request_jwt

from api.v1.mobile.account.schemas import (
    AccountDeletionConfirmInput,
    AccountDeletionOTPRequestInput,
    MobileUserMeOutput,
    MobileUserMeUpdateInput,
)
from core.api.views import BaseController
from core.utils.rate_limit import rate_limit
from core.utils.uploads import UploadError, validate_image

ACCOUNT_DELETION_OTP_PURPOSE = "account-deletion"
otp_service = OTPService()


def serialize_mobile_user(request, user: User) -> dict:
    avatar_url = request.build_absolute_uri(user.avatar.url) if user.avatar else None  # type: ignore[union-attr]
    return MobileUserMeOutput.model_validate(
        {
            "id": getattr(user, "id", None) or getattr(user, "pk", None),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "patronymic": user.patronymic,
            "email": user.email,
            "phone": user.phone,
            "nationality": user.nationality,
            "avatar_url": avatar_url,
        }
    ).model_dump(mode="json")


class MobileUserMeView(BaseController):
    def get(self) -> dict:
        return self.ok(serialize_mobile_user(self.request, self.request.user))  # type: ignore[attr-defined]

    def put(self, parsed_body: Body[MobileUserMeUpdateInput]) -> dict:
        user: User = self.request.user
        data = parsed_body.model_dump(mode="json")

        if data.get("email") and User.objects.filter(email=data["email"]).exclude(pk=user.pk).exists():
            return self.fail(
                error=str(_("This email is already in use")),
                message=str(_("Data conflict")),
                status_code=HTTPStatus.CONFLICT,
            )

        for field, value in data.items():
            setattr(user, field, value)
        user.save()
        return self.ok(serialize_mobile_user(self.request, user))


class MobileUserAvatarView(BaseController):
    def put(self) -> dict:
        content_type = getattr(self.request, "content_type", "") or ""
        if content_type.startswith("multipart/"):
            files = self.request.parse_file_upload(self.request.META, BytesIO(self.request.body))[1]  # type: ignore[attr-defined]
            image = files.get("image")
        else:
            image = self.request.FILES.get("image")
        if image is None:
            return self.fail(error=str(_("No image provided")))

        try:
            validate_image(image)
        except UploadError as err:
            return self.fail(error=str(err), message=str(_("Upload failed")))

        user: User = self.request.user
        previous_name = user.avatar.name if user.avatar else None
        previous_storage = user.avatar.storage if user.avatar else None
        user.avatar = image
        user.save(update_fields=["avatar", "updated_at"])
        if previous_name and previous_storage and previous_name != user.avatar.name:
            previous_storage.delete(previous_name)
        return self.ok(serialize_mobile_user(self.request, user))

    def delete(self) -> dict:
        user: User = self.request.user
        previous_name = user.avatar.name if user.avatar else None
        previous_storage = user.avatar.storage if user.avatar else None
        user.avatar = None
        user.save(update_fields=["avatar", "updated_at"])
        if previous_name and previous_storage:
            previous_storage.delete(previous_name)
        return self.ok(serialize_mobile_user(self.request, user))


class AccountDeletionOTPRequestView(BaseController):
    @rate_limit(requests=3, window_seconds=3600)
    def post(self, parsed_body: Body[AccountDeletionOTPRequestInput]) -> dict:
        phone = self.request.user.phone
        if not phone:
            return self.fail(
                error=str(_("This account has no phone number")),
                message=str(_("Account deletion is unavailable")),
                status_code=HTTPStatus.CONFLICT,
            )

        code = otp_service.generate_otp()
        otp_service.clear_otp_attempts(phone, purpose=ACCOUNT_DELETION_OTP_PURPOSE)
        otp_service.set_otp(phone, code, purpose=ACCOUNT_DELETION_OTP_PURPOSE)
        try:
            otp_service.dispatch(phone, code, parsed_body.channel)
        except OTPDeliveryError:
            otp_service.pop_otp(phone, purpose=ACCOUNT_DELETION_OTP_PURPOSE)
            return self.fail(
                error=str(_("Unable to deliver verification code")),
                message=str(_("Please try again later")),
                status_code=HTTPStatus.BAD_GATEWAY,
            )
        return self.ok(
            {"channel": parsed_body.channel, "expires_in": 300, "resend_after": 60},
            status_code=HTTPStatus.OK,
        )


class AccountDeletionConfirmView(BaseController):
    @rate_limit(requests=10, window_seconds=3600)
    def post(self, parsed_body: Body[AccountDeletionConfirmInput]) -> dict:
        user: User = self.request.user
        phone = user.phone
        if not phone:
            return self.fail(
                error=str(_("This account has no phone number")),
                message=str(_("Account deletion is unavailable")),
                status_code=HTTPStatus.CONFLICT,
            )

        if otp_service.get_otp_attempts(phone, purpose=ACCOUNT_DELETION_OTP_PURPOSE) >= OTP_ATTEMPT_LIMIT:
            return self.fail(
                error=str(_("Too many verification attempts")),
                message=str(_("Please request a new code")),
                status_code=HTTPStatus.TOO_MANY_REQUESTS,
            )

        code = parsed_body.code.strip()
        bypass_code = settings.OTP_DEV_BYPASS_CODE
        if not (
            (bypass_code and code == bypass_code)
            or code == otp_service.get_otp(phone, purpose=ACCOUNT_DELETION_OTP_PURPOSE)
        ):
            otp_service.increment_otp_attempts(phone, purpose=ACCOUNT_DELETION_OTP_PURPOSE)
            return self.fail(
                error=str(_("Invalid or expired code")),
                message=str(_("Verification failed")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        otp_service.pop_otp(phone, purpose=ACCOUNT_DELETION_OTP_PURPOSE)
        otp_service.clear_otp_attempts(phone, purpose=ACCOUNT_DELETION_OTP_PURPOSE)
        token = request_jwt(self.request)
        if token is not None and getattr(token, "jti", None):
            TokenBlacklist.objects.get_or_create(jti=token.jti)
        AccountDeletionService.delete_account(user)
        return self.ok({"deleted": True}, status_code=HTTPStatus.OK)
