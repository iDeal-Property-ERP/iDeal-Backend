from functools import wraps
from http import HTTPStatus

from django.utils.translation import gettext_lazy as _
from dmr.response import APIError
from dmr.security.jwt.auth import JWTSyncAuth


class RoleAuth(JWTSyncAuth):
    """JWT authentication + role authorization in one auth object.

    Usage on a controller class where all methods need the same role:
        class MyView(BaseController):
            auth = (RoleAuth(UserRole.MANAGEMENT),)
    """

    __slots__ = ('allowed_roles',)

    def __init__(self, *roles, **kwargs):
        super().__init__(**kwargs)
        self.allowed_roles = roles

    def __call__(self, endpoint, controller):
        result = super().__call__(endpoint, controller)
        if result is None:
            return None
        if self.allowed_roles and controller.request.user.role not in self.allowed_roles:
            raise APIError(
                raw_data={
                    "success": False,
                    "message": str(_("NOT OK")),
                    "error": str(_("You do not have permission to access this endpoint")),
                },
                status_code=HTTPStatus.FORBIDDEN,
            )
        return result


def require_role(*roles):
    """Decorator for per-method role enforcement.

    Usage on individual methods when different methods need different roles:
        class MyView(BaseController):
            @require_role(UserRole.MANAGEMENT, UserRole.OWNER)
            def get(self, ...):
                ...

            @require_role(UserRole.MANAGEMENT)
            def post(self, ...):
                ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if self.request.user.role not in roles:
                self.fail(
                    error=str(_("You do not have permission to access this endpoint")),
                    status_code=HTTPStatus.FORBIDDEN,
                )
            return func(self, *args, **kwargs)
        return wrapper
    return decorator
