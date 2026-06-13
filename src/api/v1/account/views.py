from core.api.views import BaseController

from .schemas import UserMeOutput


class UserMeView(BaseController):
    def get(self) -> dict:
        user = self.request.user
        return self.ok(UserMeOutput.model_validate(user).model_dump(mode="json"))
