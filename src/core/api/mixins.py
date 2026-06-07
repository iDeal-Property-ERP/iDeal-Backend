from django.conf import settings


class JWTMixin:
    jwt_expiration = settings.JWT_SETTINGS["ACCESS_TOKEN_LIFETIME"]
    jwt_refresh_expiration = settings.JWT_SETTINGS["REFRESH_TOKEN_LIFETIME"]
    jwt_issuer = settings.JWT_SETTINGS["ISSUER"]
    jwt_algorithm = settings.JWT_SETTINGS["ALGORITHM"]
    jwt_secret = settings.JWT_SETTINGS["SECRET_KEY"]
