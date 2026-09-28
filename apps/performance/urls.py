from django.urls import path

from apps.performance.views import (
    WorkerPerformanceDetailView,
    WorkerPerformanceListCreateView,
)

urlpatterns = [
    path(
        "<int:worker_id>/performance/",
        WorkerPerformanceListCreateView.as_view(),
        name="worker-performance-list",
    ),
    path(
        "<int:worker_id>/performance/<int:record_id>/",
        WorkerPerformanceDetailView.as_view(),
        name="worker-performance-detail",
    ),
]
