from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import config
from dmr.openapi.config import OpenAPIConfig
from dmr.parsers import JsonParser
from dmr.renderers import JsonRenderer

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEBUG = config("DEBUG", default=False, cast=bool)
_secret_key = config("SECRET_KEY", default="django-insecure-change-me-in-production")
if not DEBUG and _secret_key == "django-insecure-change-me-in-production":
    raise RuntimeError("SECRET_KEY must be set to a secure value in production (DEBUG=False)")
SECRET_KEY = _secret_key
_allowed_hosts_raw = config("ALLOWED_HOSTS", default="localhost,127.0.0.1")
ALLOWED_HOSTS = [h for h in _allowed_hosts_raw.split(",") if h]
DATABASE_URL = f"postgres://{config('POSTGRES_USER')}:{config('POSTGRES_PASSWORD')}@{config('POSTGRES_HOST')}/{config('POSTGRES_DB')}"

UNFOLD_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "unfold.contrib.import_export",
    "unfold.contrib.guardian",
    "unfold.contrib.simple_history",
    "unfold.contrib.location_field",
    # 'unfold.contrib.constance',
]

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "dmr",
    "corsheaders",
    "django_softdelete",
    "django_q",
]

LOCAL_APPS = [
    "account",
    "core",
    "property",
    "contract",
    "finance",
    "maintenance",
    "marketplace",
    "agent",
    "owner",
    "tenant",
    "management",
    "notification",
    "inventory",
    "vas",
]

INSTALLED_APPS = UNFOLD_APPS + DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.auth_cookies.AuthCookieMiddleware",
]

# JWT auth cookies carry the Secure flag (HTTPS-only) outside DEBUG; dev serves
# plain http://localhost so it must be off there. Overridable per-environment.
AUTH_COOKIE_SECURE = not DEBUG

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ASGI_APPLICATION = "config.server.asgi.application"
WSGI_APPLICATION = "config.server.wsgi.application"

DATABASES = {
    "default": dj_database_url.parse(
        url=DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locales"]

STATIC_URL = "/static/"
MEDIA_URL = "/media/"

STATIC_ROOT = BASE_DIR.parent / "cdn/static"
MEDIA_ROOT = BASE_DIR.parent / "cdn/media"

# Logging
LOGGING_TELEGRAM_BOT_TOKEN = config("LOGGING_TELEGRAM_BOT_TOKEN", default="")
LOGGING_TELEGRAM_CHAT_ID = config("LOGGING_TELEGRAM_CHAT_ID", default="")
PROJECT_NAME = config("PROJECT_NAME", default="iDeal Backend")

# OTP delivery
OTP_DEV_BYPASS_CODE = config("OTP_DEV_BYPASS_CODE", default="")

## Eskiz SMS
ESKIZ_EMAIL = config("ESKIZ_EMAIL", default="")
ESKIZ_PASSWORD = config("ESKIZ_PASSWORD", default="")
ESKIZ_FROM = config("ESKIZ_FROM", default="4546")
ESKIZ_BASE_URL = config("ESKIZ_BASE_URL", default="https://notify.eskiz.uz/api")

## Telegram Gateway
TELEGRAM_GATEWAY_TOKEN = config("TELEGRAM_GATEWAY_TOKEN", default="")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://localhost:6379"),
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {
            "()": "core.utils.logging.RequestContextFilter",
        },
    },
    "formatters": {
        "colored": {
            "()": "colorlog.ColoredFormatter",
            "format": (
                "%(log_color)s[%(asctime)s] [%(levelname)s] "
                "%(name)s:%(module)s:%(filename)s:%(lineno)d "
                "%(funcName)s | %(message)s"
            ),
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "log_colors": {
                "DEBUG": "white",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        },
        "telegram": {
            "format": (
                "*🚨 Django Error Alert (500)*\n"
                "*Level:* %(levelname)s\n"
                "*Message:* %(message)s\n\n"
                "*Module:* `%(module)s:%(filename)s:%(lineno)d`\n"
                "*Function:* `%(funcName)s`\n\n"
                "*User:* %(user)s\n"
                "*Method:* %(method)s\n"
                "*Path:* %(path)s\n"
                "*IP:* %(ip)s\n\n"
                "*Traceback:*\n```\n%(traceback)s\n```"
            )
        },
    },
    "handlers": {
        # Console
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "colored",
        },
        # Telegram alerts
        "telegram_errors": {
            "level": "ERROR",
            "class": "core.utils.logging.TelegramErrorHandler",
            "bot_token": LOGGING_TELEGRAM_BOT_TOKEN,
            "chat_id": LOGGING_TELEGRAM_CHAT_ID,
            "filters": ["request_context"],
            "formatter": "telegram",
        },
    },
    "loggers": {
        # Django internal logs
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Django request errors → TELEGRAM!
        "django.request": {
            "handlers": ["telegram_errors", "console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Universal logger (entire project)
        "": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DMR_SETTINGS = {
    "parsers": [JsonParser()],
    "renderers": [JsonRenderer()],
    "validate_responses": False,
    "semantic_responses": True,
    "global_error_handler": "core.api.exceptions.global_error_handler",
    "openapi_config": OpenAPIConfig(
        title="iDeal API",
        version="0.1.0",
        openapi_version="3.1.0",
        description="iDeal Backend API",
    ),
}

AUTH_USER_MODEL = "account.User"  # noqa

JWT_SETTINGS = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ISSUER": "iDeal",
    "ALGORITHM": "HS256",
    "SECRET_KEY": SECRET_KEY,
}

# Django-Q2 Configuration
Q_CLUSTER = {
    "name": "ideal-backend",
    "workers": 2,
    "recycle": 500,
    "timeout": 60,
    "compress": True,
    "save_limit": 250,
    "queue_limit": 500,
    "label": "Django Q",
    "redis": config("REDIS_URL", default="redis://localhost:6379/0"),
}

UNFOLD = {
    "SITE_URL": "/admin/",
    "SITE_TITLE": PROJECT_NAME,
    "SITE_HEADER": PROJECT_NAME,
    "SITE_SUBHEADER": lambda request: (
        request.user.get_navigation_title() if request.user.is_authenticated else "Unknown User"
    ),
    "SIDEBAR": {
        "show_search": False,
    },
}

CORS_URLS_REGEX = r"^/api/.*$"
