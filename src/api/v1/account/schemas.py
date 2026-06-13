import datetime

import pydantic


class UserMeOutput(pydantic.BaseModel):
    id: int
    first_name: str
    last_name: str | None
    patronymic: str | None
    username: str
    phone: str | None
    email: str
    role: str
    is_verified: bool
    nationality: str | None
    telegram_id: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = pydantic.ConfigDict(from_attributes=True)
