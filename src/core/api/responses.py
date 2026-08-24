"""Reusable DMR/Pydantic response behavior for all controller families."""

from http import HTTPStatus
from typing import Any

from django.utils.translation import gettext_lazy as _
from dmr.response import APIError

from core.api.schemas import ErrorResponse, SuccessResponse


class EnvelopeResponseMixin:
    """Build v1 envelopes without bypassing DMR's response pipeline."""

    def ok(self, data: Any, *, status_code: HTTPStatus | None = None):
        response = SuccessResponse[Any](message=str(_("OK")), data=data)
        if status_code is not None:
            return self.to_response(response, status_code=status_code)
        return response

    def fail(self, error: Any, message: str | None = None, status_code: HTTPStatus = HTTPStatus.BAD_REQUEST):
        raise APIError(
            raw_data=ErrorResponse(message=message or str(_("NOT OK")), error=error),
            status_code=status_code,
        )
