"""Production settings.

Requires real values through environment variables. The process fails fast
on startup when mandatory production configuration is missing.
"""

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
