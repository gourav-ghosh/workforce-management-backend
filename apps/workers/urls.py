from django.urls import include, path

from apps.workers.views import (
    WorkerDetailView,
    WorkerListCreateView,
    WorkerResetPasswordView,
)

urlpatterns = [
    path("", WorkerListCreateView.as_view(), name="worker-list"),
    path("<int:pk>/", WorkerDetailView.as_view(), name="worker-detail"),
    path(
        "<int:pk>/reset-password/",
        WorkerResetPasswordView.as_view(),
        name="worker-reset-password",
    ),
    path("", include("apps.performance.urls")),
]
