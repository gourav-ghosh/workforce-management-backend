"""Root URL configuration."""

import re

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.common.views import health_check

api_v1_patterns = [
    path("", include("apps.accounts.urls")),
    path("workers/", include("apps.workers.urls")),
    path("projects/", include("apps.projects.urls")),
    path("tools/", include("apps.tools.urls")),
    path("ppe/", include("apps.ppe.urls")),
    path("vehicles/", include("apps.transportation.urls")),
    path("attendance/", include("apps.attendance.urls")),
    path("permits/", include("apps.permits.urls")),
    path("audit/", include("apps.audit.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health-check"),
    path("api/v1/", include(api_v1_patterns)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Media is user-uploaded at runtime, so unlike static assets it cannot be
# collected by WhiteNoise. Django 5+ no longer serves it outside DEBUG (the
# `insecure` flag was removed), so wire django.views.static.serve directly for
# the local /media/ prefix. That view path-normalises and rejects `..`, so it
# is safe behind gunicorn for a field-app traffic level. If volume grows,
# move MEDIA_ROOT to a Railway Volume (see production.py) and front it with
# nginx or object storage.
if not settings.MEDIA_URL.startswith(("http://", "https://")):
    urlpatterns += [
        re_path(
            r"^%s(?P<path>.*)$" % re.escape(settings.MEDIA_URL.lstrip("/")),
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
