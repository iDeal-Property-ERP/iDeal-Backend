from typing import Literal

import pydantic


class MobileMapConfigOutput(pydantic.BaseModel):
    provider: Literal["yandex", "google"]
    token: str


class MobileVersionConfigOutput(pydantic.BaseModel):
    update_type: Literal["none", "normal", "critical"]
    current_version: str
    latest_version: str | None = None
    store_url: str | None = None
