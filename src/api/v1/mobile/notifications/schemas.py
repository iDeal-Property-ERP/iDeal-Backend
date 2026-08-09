from __future__ import annotations

from datetime import datetime

import pydantic


class MobileNotificationFilterQuery(pydantic.BaseModel):
    page: int = 1
    per_page: int = 20
    is_read: bool | None = None
    category: str | None = None


class MobileNotificationOutput(pydantic.BaseModel):
    id: int
    type: str
    category: str
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
