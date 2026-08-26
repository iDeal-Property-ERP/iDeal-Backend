from datetime import timedelta
from pathlib import Path

# pi-lens-ignore: reportMissingImports
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
_allowed_hosts_raw = str(config("ALLOWED_HOSTS", default="localhost,127.0.0.1"))
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
    "channels",
    "dmr",
    "corsheaders",
    "django_softdelete",
    "django_q",
    "storages",
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
    "chat",
    "mobile_config",
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

# Storage Configuration (Garage S3 / Local FileSystem)
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default="")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="garage")
AWS_S3_SIGNATURE_VERSION = config("AWS_S3_SIGNATURE_VERSION", default="s3v4")
AWS_S3_ADDRESSING_STYLE = config("AWS_S3_ADDRESSING_STYLE", default="path")
AWS_QUERYSTRING_AUTH = config("AWS_QUERYSTRING_AUTH", default=True, cast=bool)
AWS_QUERYSTRING_EXPIRE = config("AWS_QUERYSTRING_EXPIRE", default=3600, cast=int)
AWS_S3_FILE_OVERWRITE = config("AWS_S3_FILE_OVERWRITE", default=False, cast=bool)

if AWS_STORAGE_BUCKET_NAME and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "access_key": AWS_ACCESS_KEY_ID,
                "secret_key": AWS_SECRET_ACCESS_KEY,
                "bucket_name": AWS_STORAGE_BUCKET_NAME,
                "endpoint_url": AWS_S3_ENDPOINT_URL or None,
                "region_name": AWS_S3_REGION_NAME,
                "signature_version": AWS_S3_SIGNATURE_VERSION,
                "addressing_style": AWS_S3_ADDRESSING_STYLE,
                "querystring_auth": AWS_QUERYSTRING_AUTH,
                "querystring_expire": AWS_QUERYSTRING_EXPIRE,
                "file_overwrite": AWS_S3_FILE_OVERWRITE,
            },
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }


# Logging
LOGGING_TELEGRAM_BOT_TOKEN = config("LOGGING_TELEGRAM_BOT_TOKEN", default="")
LOGGING_TELEGRAM_CHAT_ID = config("LOGGING_TELEGRAM_CHAT_ID", default="")
PROJECT_NAME = config("PROJECT_NAME", default="iDeal Backend")

# OTP delivery
OTP_DEV_BYPASS_CODE = config("OTP_DEV_BYPASS_CODE", default="")
RATE_LIMIT_ENABLED = True
OTP_TELEGRAM_ENABLED = config("OTP_TELEGRAM_ENABLED", default=True, cast=bool)
OTP_SMS_ENABLED = config("OTP_SMS_ENABLED", default=True, cast=bool)

## Eskiz SMS
ESKIZ_EMAIL = config("ESKIZ_EMAIL", default="")
ESKIZ_PASSWORD = config("ESKIZ_PASSWORD", default="")
ESKIZ_FROM = config("ESKIZ_FROM", default="4546")
ESKIZ_BASE_URL = config("ESKIZ_BASE_URL", default="https://notify.eskiz.uz/api")

## Telegram Gateway
TELEGRAM_GATEWAY_TOKEN = config("TELEGRAM_GATEWAY_TOKEN", default="")

## Firebase Cloud Messaging
FCM_ENABLED = config("FCM_ENABLED", default=False, cast=bool)
FCM_CREDENTIALS_PATH = config("FCM_CREDENTIALS_PATH", default="")
FCM_PROJECT_ID = config("FCM_PROJECT_ID", default="")

CHAT_MAX_IMAGE_BYTES = config("CHAT_MAX_IMAGE_BYTES", default=5 * 1024 * 1024, cast=int)
PLATFORM_CONTACT_PHONE = config("PLATFORM_CONTACT_PHONE", default="")
SUPPORT_TELEGRAM_URL = config("SUPPORT_TELEGRAM_URL", default="")
SUPPORT_WHATSAPP_URL = config("SUPPORT_WHATSAPP_URL", default="")

# Hosted booking payments. Providers stay hidden until both their deployment
# configuration and enable flag are present.
PAYME_ENABLED = config("PAYME_ENABLED", default=False, cast=bool)
PAYME_MERCHANT_ID = config("PAYME_MERCHANT_ID", default="")
PAYME_KEY = config("PAYME_KEY", default="")
PAYME_CHECKOUT_URL = config("PAYME_CHECKOUT_URL", default="https://checkout.paycom.uz")
CLICK_ENABLED = config("CLICK_ENABLED", default=False, cast=bool)
CLICK_SERVICE_ID = config("CLICK_SERVICE_ID", default="")
CLICK_MERCHANT_ID = config("CLICK_MERCHANT_ID", default="")
CLICK_SECRET_KEY = config("CLICK_SECRET_KEY", default="")
CLICK_CHECKOUT_URL = config("CLICK_CHECKOUT_URL", default="https://my.click.uz/services/pay")
STRIPE_ENABLED = config("STRIPE_ENABLED", default=False, cast=bool)
STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = config("STRIPE_WEBHOOK_SECRET", default="")

# Map Provider Configuration
MAP_DEFAULT_PROVIDER = config("MAP_DEFAULT_PROVIDER", default="yandex")
YANDEX_MAPKIT_API_KEY = config("YANDEX_MAPKIT_API_KEY", default="")
GOOGLE_MAPS_API_KEY = config("GOOGLE_MAPS_API_KEY", default="")
MAP_OBFUSCATION_SECRET = config("MAP_OBFUSCATION_SECRET", default="")

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
    "catch_up": False,
}

# The Redis channel layer lets every ASGI worker deliver the same chat events.
# Keep it separate from the cache configuration so capacity can be tuned for
# realtime traffic without changing cache eviction behaviour.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                {
                    "address": config("REDIS_URL", default="redis://localhost:6379/0"),
                    "socket_timeout": config("CHANNEL_REDIS_SOCKET_TIMEOUT", default=10, cast=int),
                    "socket_connect_timeout": config("CHANNEL_REDIS_CONNECT_TIMEOUT", default=5, cast=int),
                }
            ],
            "capacity": config("CHAT_CHANNEL_CAPACITY", default=200, cast=int),
            "expiry": config("CHAT_CHANNEL_EXPIRY_SECONDS", default=60, cast=int),
        },
    },
}
CHAT_REALTIME_EVENT_RETENTION_DAYS = config("CHAT_REALTIME_EVENT_RETENTION_DAYS", default=7, cast=int)
CHAT_REALTIME_REPLAY_LIMIT = config("CHAT_REALTIME_REPLAY_LIMIT", default=500, cast=int)

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
