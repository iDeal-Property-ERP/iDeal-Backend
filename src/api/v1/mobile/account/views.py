from http import HTTPStatus
from io import BytesIO

from account.models import User
from django.utils.translation import gettext_lazy as _
from dmr import Body

from api.v1.mobile.account.schemas import MobileUserMeOutput, MobileUserMeUpdateInput
from core.api.views import BaseController
from core.utils.uploads import UploadError, validate_image


def serialize_mobile_user(request, user: User) -> dict:
    avatar_url = request.build_absolute_uri(user.avatar.url) if user.avatar else None
    return MobileUserMeOutput.model_validate(
        {
            "id": user.id,
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
        return self.ok(serialize_mobile_user(self.request, self.request.user))

    def put(self, parsed_body: Body[MobileUserMeUpdateInput]) -> dict:
        user = self.request.user
        data = parsed_body.model_dump(mode="json")

        if User.objects.filter(email=data["email"]).exclude(pk=user.pk).exists():
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
        if self.request.content_type.startswith("multipart/"):
            files = self.request.parse_file_upload(self.request.META, BytesIO(self.request.body))[1]
            image = files.get("image")
        else:
            image = self.request.FILES.get("image")
        if image is None:
            return self.fail(error=str(_("No image provided")))

        try:
            validate_image(image)
        except UploadError as err:
            return self.fail(error=str(err), message=str(_("Upload failed")))

        user = self.request.user
        previous_name = user.avatar.name if user.avatar else None
        previous_storage = user.avatar.storage if user.avatar else None
        user.avatar = image
        user.save(update_fields=["avatar", "updated_at"])
        if previous_name and previous_storage and previous_name != user.avatar.name:
            previous_storage.delete(previous_name)
        return self.ok(serialize_mobile_user(self.request, user))

    def delete(self) -> dict:
        user = self.request.user
        previous_name = user.avatar.name if user.avatar else None
        previous_storage = user.avatar.storage if user.avatar else None
        user.avatar = None
        user.save(update_fields=["avatar", "updated_at"])
        if previous_name and previous_storage:
            previous_storage.delete(previous_name)
        return self.ok(serialize_mobile_user(self.request, user))
