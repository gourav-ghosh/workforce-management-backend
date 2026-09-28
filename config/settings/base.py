"""
Base settings shared by all environments.

Every environment-specific value is read from environment variables
(optionally provided through a `.env` file at the repository root).
"""

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, "django-insecure-dev-only-key-do-not-use-in-production"),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DB_CONN_MAX_AGE=(int, 60),
    CORS_ALLOWED_ORIGINS=(list, []),
    MEDIA_ROOT=(str, str(BASE_DIR / "media")),
    MEDIA_URL=(str, "/media/"),
    STATIC_ROOT=(str, str(BASE_DIR / "staticfiles")),
    STATIC_URL=(str, "/static/"),
    MAX_UPLOAD_SIZE_MB=(int, 10),
    JWT_ACCESS_TOKEN_LIFETIME_MINUTES=(int, 60),
    JWT_REFRESH_TOKEN_LIFETIME_DAYS=(int, 14),
    PAGE_SIZE=(int, 20),
    LOG_LEVEL=(str, "INFO"),
    PUBLIC_BASE_URL=(str, ""),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = list(env("DJANGO_ALLOWED_HOSTS"))
PAGE_SIZE = env("PAGE_SIZE")

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
]

LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.workers",
    "apps.projects",
    "apps.tools",
    "apps.ppe",
    "apps.transportation",
    "apps.audit",
    "apps.dashboard",
    "apps.performance",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "apps.common.middleware.PublicHostMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "config.wsgi.application"

# Authentication
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = (
    "apps.accounts.backends.MobileNumberAuthBackend",
    "django.contrib.auth.backends.ModelBackend",
)


# Database
# Resolution order (first match wins):
#   1. DATABASE_URL               - single connection URL. Always preferred, and
#                                  the only variable Docker/Railway inject.
#   2. POSTGRES_* / DB_* / PG*    - discrete parts, for hosts that expose
#                                  individual settings instead of one URL.
#   3. SQLite file                - last-resort local fallback so a fresh
#                                  checkout still runs without Postgres.
# `postgres://` is normalised to `postgresql://` because that is the scheme
# psycopg expects; some providers still emit the legacy alias.
def _database_url_from_parts():
    name = (
        env.str("POSTGRES_DB", default="")
        or env.str("DB_NAME", default="")
        or env.str("PGDATABASE", default="")
    )
    user = (
        env.str("POSTGRES_USER", default="")
        or env.str("DB_USER", default="")
        or env.str("PGUSER", default="")
    )
    if not name or not user:
        return None

    password = (
        env.str("POSTGRES_PASSWORD", default="")
        or env.str("DB_PASSWORD", default="")
        or env.str("PGPASSWORD", default="")
    )
    host = env.str("DB_HOST", default="") or env.str("PGHOST", default="") or "localhost"
    port = env.str("DB_PORT", default="") or env.str("PGPORT", default="") or "5432"

    credentials = quote(user, safe="")
    if password:
        credentials = f"{credentials}:{quote(password, safe='')}"
    return f"postgresql://{credentials}@{host}:{port}/{name}"


DATABASE_URL = env.str("DATABASE_URL", default="")
if not DATABASE_URL:
    DATABASE_URL = _database_url_from_parts() or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://") :]

# env.db_url() reads from os.environ, so publish the resolved value first.
os.environ["DATABASE_URL"] = DATABASE_URL

DATABASES = {
    "default": env.db_url("DATABASE_URL"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env("DB_CONN_MAX_AGE")

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Worker passwords are supplied by the admin at creation time (see
# apps/workers/serializers.WorkerWriteSerializer and
# POST /api/v1/workers/). There is no env-level default.

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": env("PAGE_SIZE"),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "auth": "60/min",
        "password_reset": "10/min",
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

if DEBUG:
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    )

# SimpleJWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env("JWT_ACCESS_TOKEN_LIFETIME_MINUTES")),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env("JWT_REFRESH_TOKEN_LIFETIME_DAYS")),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.LoginTokenObtainPairSerializer",
}

# CORS
CORS_ALLOWED_ORIGINS = list(env("CORS_ALLOWED_ORIGINS"))

# Static & media
STATIC_URL = env("STATIC_URL")
STATIC_ROOT = Path(env("STATIC_ROOT"))
MEDIA_URL = env("MEDIA_URL")
MEDIA_ROOT = Path(env("MEDIA_ROOT"))

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Upload limits (validated again at serializer level)
MAX_UPLOAD_SIZE_MB = env("MAX_UPLOAD_SIZE_MB")
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"]

# Public origin used when building absolute URLs for media (image file_url
# fields). When empty, Django falls back to the request's host, which is
# fine for local DEBUG work but breaks behind a reverse proxy or when the
# mobile app is on a different host (e.g. Android emulator → 10.0.2.2).
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL")

# i18n / tz
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# OpenAPI
SPECTACULAR_SETTINGS = {
    "TITLE": "Workforce Management API",
    "DESCRIPTION": "REST API for the Workforce Management mobile application (Version 1.2).",
    "VERSION": "1.2.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
}

# Logging
LOG_LEVEL = env("LOG_LEVEL")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}
