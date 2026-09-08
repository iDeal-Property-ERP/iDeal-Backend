import pydantic


class SupportInquiryInput(pydantic.BaseModel):
    name: str = pydantic.Field(min_length=2, max_length=255)
    email: pydantic.EmailStr
    message: str = pydantic.Field(min_length=10, max_length=5000)
    website_url: str | None = None

    model_config = pydantic.ConfigDict(str_strip_whitespace=True)


class SupportInquiryOutput(pydantic.BaseModel):
    id: int | None = None
    status: str
    message: str
