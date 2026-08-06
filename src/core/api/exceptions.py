import logging
from http import HTTPStatus

from django.conf import settings
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.http import Http404, JsonResponse
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

logger = logging.getLogger("django.request")


def global_error_handler(endpoint, controller, exc):
    if isinstance(exc, NotAuthenticatedError):
        return JsonResponse(
            {"success": False, "message": str(_("Not authenticated")), "error": str(exc)},
            status=HTTPStatus.UNAUTHORIZED,
        )
    if isinstance(exc, TooManyRequestsError):
        return JsonResponse(
            {"success": False, "message": str(_("Too many requests")), "error": str(exc)},
            status=HTTPStatus.TOO_MANY_REQUESTS,
        )
    if isinstance(exc, ValidationError):
        return JsonResponse(
            {"success": False, "message": str(_("Validation error")), "error": exc.payload},
            status=exc.status_code,
        )
    if isinstance(exc, RequestSerializationError):
        return JsonResponse(
            {"success": False, "message": str(_("Invalid request body")), "error": str(exc)},
            status=HTTPStatus.BAD_REQUEST,
        )
    if isinstance(exc, NotAcceptableError):
        return JsonResponse(
            {"success": False, "message": str(_("Not acceptable")), "error": str(exc)},
            status=HTTPStatus.NOT_ACCEPTABLE,
        )
    if isinstance(exc, (InternalServerError, DataRenderingError, ResponseSchemaError)):
        error_text = str(exc) if settings.DEBUG else force_str(InternalServerError.default_message)
        logger.error(
            "Internal Server Error: %s",
            error_text,
            exc_info=exc,
            extra={"request": getattr(controller, "request", None)},
        )
        resp = JsonResponse(
            {"success": False, "message": str(_("Internal server error")), "error": error_text},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
        resp._has_been_logged = True
        return resp

    if isinstance(exc, Http404):
        return JsonResponse(
            {"success": False, "message": str(_("Not found")), "error": str(exc)},
            status=HTTPStatus.NOT_FOUND,
        )

    # Database-level guards. These must NEVER echo the raw exception (it leaks the
    # failing row / SQL / constraint internals), regardless of DEBUG.
    if isinstance(exc, ProtectedError):
        return JsonResponse(
            {
                "success": False,
                "message": str(_("Cannot delete")),
                "error": str(_("This record is referenced by other records and cannot be deleted.")),
            },
            status=HTTPStatus.CONFLICT,
        )
    if isinstance(exc, IntegrityError):
        return JsonResponse(
            {
                "success": False,
                "message": str(_("Data conflict")),
                "error": str(_("The request conflicts with existing data or references a missing record.")),
            },
            status=HTTPStatus.CONFLICT,
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

    resp = JsonResponse(
        {"success": False, "message": str(_("Internal server error")), "error": error_text},
        status=status_code,
    )
    if status_code == HTTPStatus.INTERNAL_SERVER_ERROR:
        resp._has_been_logged = True
    return resp
