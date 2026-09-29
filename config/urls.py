"""Root URL configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
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

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
