"""Production settings.

Requires real values through environment variables. The process fails fast
on startup when mandatory production configuration is missing.
"""

import os as _os
import warnings

from .base import *
from .base import env

_DEBUG = env.bool("DJANGO_DEBUG", default=False)

if _DEBUG:
    raise RuntimeError(
        "DJANGO_DEBUG must be false in production. Use config.settings.development "
        "for local development."
    )

SECRET_KEY = env("DJANGO_SECRET_KEY")
if SECRET_KEY.startswith("django-insecure"):
    raise RuntimeError("A strong DJANGO_SECRET_KEY must be provided in production.")

if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["*"]:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must list the production host(s).")

# PublicHostMiddleware rewrites request.META['HTTP_HOST'] to the host parsed
# from PUBLIC_BASE_URL, and Django then validates that host against
# ALLOWED_HOSTS. If the public host is missing from the list, *every* request
# fails with 400 DisallowedHost - including the platform healthcheck, so the
# deployment never becomes healthy. Fail at startup with a clear message
# instead of serving 400s.
if PUBLIC_BASE_URL:
    from urllib.parse import urlparse

    _public_host = urlparse(PUBLIC_BASE_URL).netloc.split("@")[-1]
    if _public_host and _public_host not in ALLOWED_HOSTS:
        raise RuntimeError(
            f"DJANGO_ALLOWED_HOSTS is missing the PUBLIC_BASE_URL host "
            f"'{_public_host}'. Add it, or the app will return HTTP 400 for "
            f"every request."
        )

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

if not CORS_ALLOWED_ORIGINS:
    raise RuntimeError("CORS_ALLOWED_ORIGINS must be configured in production.")

# Ephemeral-storage warning.
#
# Railway rebuilds the container on every deploy and discards the local
# filesystem, so anything written under the default MEDIA_ROOT
# (/app/media) is gone on the next deploy — which is exactly when uploaded
# tool/PPE/vehicle photos and permit sheets would start 404ing. The only
# ways to make them survive are (a) mount a Railway Volume at MEDIA_ROOT and
# point the MEDIA_ROOT env var there, or (b) use object storage. We cannot
# create a Volume from code, so this is surfaced loudly at startup.
_ephemeral_hint = _os.environ.get("RAILWAY_ENVIRONMENT") or _os.environ.get("RAILWAY_SERVICE_ID")
_media_inside_app = str(MEDIA_ROOT).startswith("/app")
if _ephemeral_hint and _media_inside_app:
    warnings.warn(
        "MEDIA_ROOT is inside the container image. Attach a Railway Volume "
        "and set MEDIA_ROOT to its mount path, or uploaded files will be "
        "lost on every redeploy.",
        stacklevel=2,
    )

# base.py falls back to SQLite when no database environment variable is set.
# That fallback is for local development only. Silently accepting it here
# hides a missing DATABASE_URL, and with DATABASE_SSLMODE set the failure
# surfaces deep inside the SQLite driver as
# "TypeError: 'sslmode' is an invalid keyword argument" instead of the real
# cause. Fail at startup with an actionable message.
if not DATABASES["default"]["ENGINE"].endswith("postgresql"):
    raise RuntimeError(
        "Production requires PostgreSQL, but the resolved database engine is "
        f"'{DATABASES['default']['ENGINE']}'. This usually means DATABASE_URL "
        "is empty. Set DATABASE_URL (preferred, e.g. "
        "postgresql://user:password@host:5432/dbname) or the discrete "
        "POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD / DB_HOST variables."
    )

DATABASES["default"].setdefault("OPTIONS", {})
_sslmode = env.str("DATABASE_SSLMODE", default=None)
if _sslmode:
    DATABASES["default"]["OPTIONS"]["sslmode"] = _sslmode

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env.str("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="no-reply@example.com")
