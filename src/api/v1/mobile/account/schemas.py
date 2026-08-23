from typing import Any, Literal

import pydantic


class MobileUserMeOutput(pydantic.BaseModel):
    id: int
    first_name: str
    last_name: str | None
    patronymic: str | None
    email: str | None = None
    phone: str | None
    nationality: str | None
    avatar_url: str | None

    model_config = pydantic.ConfigDict(from_attributes=True)


class MobileUserMeUpdateInput(pydantic.BaseModel):
    first_name: str = pydantic.Field(min_length=1, max_length=30)
    last_name: str | None = pydantic.Field(default=None, max_length=30)
    patronymic: str | None = pydantic.Field(default=None, max_length=100)
    email: pydantic.EmailStr | None = pydantic.Field(default=None, max_length=254)
    nationality: str | None = pydantic.Field(default=None, max_length=50)

    model_config = pydantic.ConfigDict(extra="forbid", str_strip_whitespace=True)

    @pydantic.field_validator("last_name", "patronymic", "email", "nationality", mode="before")
    @classmethod
    def blank_optional_fields_are_null(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value if value else None
        return value


class AccountDeletionOTPRequestInput(pydantic.BaseModel):
    channel: Literal["sms", "telegram"] = "telegram"


class AccountDeletionConfirmInput(pydantic.BaseModel):
    code: str = pydantic.Field(min_length=6, max_length=6)

    model_config = pydantic.ConfigDict(str_strip_whitespace=True)


class PhoneChangeOTPRequestInput(pydantic.BaseModel):
    phone: str
    channel: Literal["sms", "telegram"] = "telegram"

    model_config = pydantic.ConfigDict(str_strip_whitespace=True)


class PhoneChangeConfirmInput(pydantic.BaseModel):
    phone: str
    code: str = pydantic.Field(pattern=r"^\d{6}$")

    model_config = pydantic.ConfigDict(str_strip_whitespace=True)
