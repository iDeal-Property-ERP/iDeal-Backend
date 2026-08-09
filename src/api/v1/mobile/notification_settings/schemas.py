import pydantic


class NotificationSettingsUpdateInput(pydantic.BaseModel):
    push_enabled: bool | None = None
    payments_enabled: bool | None = None
    bookings_enabled: bool | None = None
    maintenance_enabled: bool | None = None
    leases_enabled: bool | None = None
    general_enabled: bool | None = None

    model_config = pydantic.ConfigDict(extra="forbid")


class NotificationSettingsOutput(pydantic.BaseModel):
    push_enabled: bool
    payments_enabled: bool
    bookings_enabled: bool
    maintenance_enabled: bool
    leases_enabled: bool
    general_enabled: bool

    model_config = pydantic.ConfigDict(from_attributes=True)
