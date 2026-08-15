import pydantic


class MobileSupportLinksOutput(pydantic.BaseModel):
    telegram_url: str | None = None
    whatsapp_url: str | None = None
