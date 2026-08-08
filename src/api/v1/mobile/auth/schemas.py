from typing import Literal

from pydantic import BaseModel


class OTPRequestInput(BaseModel):
    phone: str
    channel: Literal["sms", "telegram"] = "telegram"


class OTPVerifyInput(BaseModel):
    phone: str
    code: str
