from __future__ import annotations

from datetime import datetime

import pydantic


class NotificationOutput(pydantic.BaseModel):
    id: int
    type: str
    title: str
    body: str | None
    related_object_type: str | None
    related_object_id: int | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class UnreadCountOutput(pydantic.BaseModel):
    unread_count: int


class NotificationFilterQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20
    is_read: bool | None = None
