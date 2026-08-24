import datetime
from typing import Literal

import pydantic


class UserMeOutput(pydantic.BaseModel):
    id: int
    first_name: str
    last_name: str | None
    patronymic: str | None
    username: str
    phone: str | None
    email: str | None = None
    role: str
    is_verified: bool
    must_change_password: bool
    nationality: str | None
    telegram_id: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class PublicAccountDeletionOTPRequestInput(pydantic.BaseModel):
    phone: str
    channel: Literal["sms", "telegram"] = "telegram"

    model_config = pydantic.ConfigDict(str_strip_whitespace=True)


class PublicAccountDeletionConfirmInput(pydantic.BaseModel):
    phone: str
    code: str = pydantic.Field(min_length=6, max_length=6)

    model_config = pydantic.ConfigDict(str_strip_whitespace=True)


class PublicAccountDeletionOTPRequestOutput(pydantic.BaseModel):
    channel: str
    expires_in: int
    resend_after: int


class PublicAccountDeletionConfirmOutput(pydantic.BaseModel):
    deleted: bool


class PublicAccountDeletionChannelsOutput(pydantic.BaseModel):
    channels: list[str]
