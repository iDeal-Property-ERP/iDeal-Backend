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

# Local development must not block repeated manual OTP and marketplace flows.
RATE_LIMIT_ENABLED = False

JWT_SETTINGS = {
    # Access tokens are short-lived; the client silently refreshes on 401. A
    # 30-day access token (previously set here for dev convenience) means a
    # leaked token is usable for a month with no way to revoke it early.
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ISSUER": "iDeal",
    "ALGORITHM": "HS256",
    "SECRET_KEY": SECRET_KEY,
}
