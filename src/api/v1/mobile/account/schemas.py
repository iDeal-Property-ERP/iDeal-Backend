from typing import Literal

import pydantic


class MobileUserMeOutput(pydantic.BaseModel):
    id: int
    first_name: str
    last_name: str | None
    patronymic: str | None
    email: str
    phone: str | None
    nationality: str | None
    avatar_url: str | None

    model_config = pydantic.ConfigDict(from_attributes=True)


class MobileUserMeUpdateInput(pydantic.BaseModel):
    first_name: str = pydantic.Field(min_length=1, max_length=30)
    last_name: str | None = pydantic.Field(default=None, max_length=30)
    patronymic: str | None = pydantic.Field(default=None, max_length=100)
    email: pydantic.EmailStr = pydantic.Field(max_length=254)
    nationality: str | None = pydantic.Field(default=None, max_length=50)

    model_config = pydantic.ConfigDict(extra="forbid", str_strip_whitespace=True)

    @pydantic.field_validator("last_name", "patronymic", "nationality", mode="after")
    @classmethod
    def blank_optional_fields_are_null(cls, value: str | None) -> str | None:
        return value or None


class AccountDeletionOTPRequestInput(pydantic.BaseModel):
    channel: Literal["sms", "telegram"] = "telegram"


class AccountDeletionConfirmInput(pydantic.BaseModel):
    code: str = pydantic.Field(min_length=6, max_length=6)

    model_config = pydantic.ConfigDict(str_strip_whitespace=True)
