import logging
from http import HTTPStatus

from django.conf import settings
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.utils.encoding import force_str
from django.utils.translation import gettext_lazy as _
from dmr.exceptions import (
    DataRenderingError,
    InternalServerError,
    NotAcceptableError,
    NotAuthenticatedError,
    RequestSerializationError,
    ResponseSchemaError,
    TooManyRequestsError,
    ValidationError,
)

from core.api.schemas import ErrorResponse

logger = logging.getLogger("django.request")


def _error_response(controller, *, error, message, status_code):
    """Use DMR's response path for every error envelope."""
    return controller.to_error(
        ErrorResponse(message=str(message), error=error),
        status_code=status_code,
    )


def global_error_handler(endpoint, controller, exc):
    if isinstance(exc, NotAuthenticatedError):
        return _error_response(
            controller, error=str(exc), message=_("Not authenticated"), status_code=HTTPStatus.UNAUTHORIZED
        )
    if isinstance(exc, TooManyRequestsError):
        return _error_response(
            controller, error=str(exc), message=_("Too many requests"), status_code=HTTPStatus.TOO_MANY_REQUESTS
        )
    if isinstance(exc, ValidationError):
        return _error_response(
            controller, error=exc.payload, message=_("Validation error"), status_code=exc.status_code
        )
    if isinstance(exc, RequestSerializationError):
        return _error_response(
            controller, error=str(exc), message=_("Invalid request body"), status_code=HTTPStatus.BAD_REQUEST
        )
    if isinstance(exc, NotAcceptableError):
        return _error_response(
            controller, error=str(exc), message=_("Not acceptable"), status_code=HTTPStatus.NOT_ACCEPTABLE
        )
    if isinstance(exc, (InternalServerError, DataRenderingError, ResponseSchemaError)):
        error_text = str(exc) if settings.DEBUG else force_str(InternalServerError.default_message)
        logger.error(
            "Internal Server Error: %s",
            error_text,
            exc_info=exc,
            extra={"request": getattr(controller, "request", None)},
        )
        resp = _error_response(
            controller,
            error=error_text,
            message=_("Internal server error"),
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
        resp._has_been_logged = True
        return resp

    if isinstance(exc, Http404):
        return _error_response(controller, error=str(exc), message=_("Not found"), status_code=HTTPStatus.NOT_FOUND)

    # Database-level guards. These must NEVER echo the raw exception (it leaks the
    # failing row / SQL / constraint internals), regardless of DEBUG.
    if isinstance(exc, ProtectedError):
        return _error_response(
            controller,
            error=str(_("This record is referenced by other records and cannot be deleted.")),
            message=_("Cannot delete"),
            status_code=HTTPStatus.CONFLICT,
        )
    if isinstance(exc, IntegrityError):
        return _error_response(
            controller,
            error=str(_("The request conflicts with existing data or references a missing record.")),
            message=_("Data conflict"),
            status_code=HTTPStatus.CONFLICT,
        )

    status_code = getattr(exc, "status_code", HTTPStatus.INTERNAL_SERVER_ERROR)
    error_text = str(exc) if settings.DEBUG else str(_("Internal server error"))

    if status_code == HTTPStatus.INTERNAL_SERVER_ERROR:
        logger.error(
            "Internal Server Error: %s",
            error_text,
            exc_info=exc,
            extra={"request": getattr(controller, "request", None)},
        )

    resp = _error_response(controller, error=error_text, message=_("Internal server error"), status_code=status_code)
    if status_code == HTTPStatus.INTERNAL_SERVER_ERROR:
        resp._has_been_logged = True
    return resp
