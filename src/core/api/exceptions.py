from http import HTTPStatus

from django.conf import settings
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
        return JsonResponse(
            {"success": False, "message": str(_("Internal server error")), "error": error_text},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, Http404):
        return JsonResponse(
            {"success": False, "message": str(_("Not found")), "error": str(exc)},
            status=HTTPStatus.NOT_FOUND,
        )

    status_code = getattr(exc, "status_code", HTTPStatus.INTERNAL_SERVER_ERROR)
    error_text = str(exc) if settings.DEBUG else str(_("Internal server error"))
    return JsonResponse(
        {"success": False, "message": str(_("Internal server error")), "error": error_text},
        status=status_code,
    )
