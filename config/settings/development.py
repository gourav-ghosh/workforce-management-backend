"""Development settings."""

from .base import *
from .base import env

DEBUG = True

ALLOWED_HOSTS = list(
    set(list(ALLOWED_HOSTS) + ["localhost", "127.0.0.1", "10.0.2.2", "testserver"])
)

# Convenience for local development only: if no explicit origins are
# configured, allow every origin so Flutter web/emulator clients work.
if not CORS_ALLOWED_ORIGINS:
    CORS_ALLOW_ALL_ORIGINS = True

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")

LOG_LEVEL = "DEBUG"
