from datetime import timedelta

from .base import *  # noqa

if DEBUG:
    INSTALLED_APPS += [
        "debug_toolbar",
        "django_extensions",
        "query_counter",
    ]

    MIDDLEWARE += [
        "debug_toolbar.middleware.DebugToolbarMiddleware",
        "query_counter.middleware.DjangoQueryCounterMiddleware",
    ]

INTERNAL_IPS = ["127.0.0.1"]

CORS_ALLOW_ALL_ORIGINS = True

JWT_SETTINGS = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ISSUER": "iDeal",
    "ALGORITHM": "HS256",
    "SECRET_KEY": SECRET_KEY,
}
