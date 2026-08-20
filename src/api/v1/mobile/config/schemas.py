from typing import Literal

import pydantic


class MobileMapConfigOutput(pydantic.BaseModel):
    provider: Literal["yandex", "google"]
    token: str
