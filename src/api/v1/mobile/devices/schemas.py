from datetime import datetime
from typing import Literal

import pydantic


class DeviceRegistrationInput(pydantic.BaseModel):
    token: str = pydantic.Field(min_length=1)
    platform: Literal["android", "ios"]
    device_id: str | None = None
    app_version: str | None = None
    locale: str | None = None


class DeviceUnregisterInput(pydantic.BaseModel):
    token: str = pydantic.Field(min_length=1)


class DeviceOutput(pydantic.BaseModel):
    id: int
    platform: str
    is_active: bool
    created_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)
