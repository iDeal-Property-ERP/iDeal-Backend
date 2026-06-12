from __future__ import annotations

import pydantic


class ManagementUserUpdateInput(pydantic.BaseModel):
    is_active: bool | None = None
    is_verified: bool | None = None
    role: str | None = None
