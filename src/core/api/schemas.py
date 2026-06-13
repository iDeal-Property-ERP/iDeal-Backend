import pydantic


class DeleteData(pydantic.BaseModel):
    deleted: bool = True
