import datetime as dt

from django.conf import settings


class JWTMixin:
    jwt_expiration = settings.JWT_SETTINGS["ACCESS_TOKEN_LIFETIME"]
    jwt_refresh_expiration = settings.JWT_SETTINGS["REFRESH_TOKEN_LIFETIME"]
    jwt_issuer = settings.JWT_SETTINGS["ISSUER"]
    jwt_algorithm = settings.JWT_SETTINGS["ALGORITHM"]
    jwt_secret = settings.JWT_SETTINGS["SECRET_KEY"]

    def create_jwt_token(self, *, expiration=None, token_type=None, subject=None, **kwargs):
        """Mint a token, adding ``role`` + ``must_change_password`` to the access
        token so the frontend middleware can gate routes without a round-trip.

        Mirrors dmr's ``create_jwt_token`` (which only sets ``extras={'type': ...}``)
        but merges the extra claims. ``request.user`` is set by the login/refresh
        controllers before this runs, so it is the authenticated user in both flows.
        """
        extras = {"type": token_type} if token_type else {}
        if token_type == "access":
            user = getattr(self.request, "user", None)
            if user is not None and getattr(user, "is_authenticated", False):
                extras["role"] = user.role
                extras["must_change_password"] = user.must_change_password
        return self.jwt_token_cls(
            sub=subject or str(self.request.user.pk),
            exp=expiration or (dt.datetime.now(dt.UTC) + self.jwt_expiration),
            iss=self.jwt_issuer,
            aud=self.jwt_audiences,
            jti=self.make_jwt_id(),
            extras=extras,
        ).encode(
            secret=self.jwt_secret or settings.SECRET_KEY,
            algorithm=self.jwt_algorithm,
        )
