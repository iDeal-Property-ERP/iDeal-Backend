from typing import Any

import pydantic


class APIModel(pydantic.BaseModel):
    """Common Pydantic policy for API schemas.

    Version one deliberately ignores unknown input keys.  This is an explicit
    compatibility policy; endpoint query models can become strict only in a
    future API version.
    """

    model_config = pydantic.ConfigDict(extra="ignore")


class SuccessResponse[DataT](APIModel):
    success: bool = True
    message: str = "OK"
    data: DataT


class ErrorResponse(APIModel):
    success: bool = False
    message: str = "NOT OK"
    error: Any


class PaginationPage[DataT](APIModel):
    number: int
    object_list: list[DataT]


class Pagination[DataT](APIModel):
    count: int
    num_pages: int
    per_page: int
    page: PaginationPage[DataT]


class DeleteData(APIModel):
    deleted: bool = True
