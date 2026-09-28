from django.urls import path

from apps.projects.views import (
    ProjectDetailView,
    ProjectListCreateView,
    ProjectWorkerListView,
    ProjectWorkerRemoveView,
)

urlpatterns = [
    path("", ProjectListCreateView.as_view(), name="project-list"),
    path("<int:pk>/", ProjectDetailView.as_view(), name="project-detail"),
    path("<int:pk>/workers/", ProjectWorkerListView.as_view(), name="project-workers"),
    path(
        "<int:pk>/workers/<int:worker_id>/",
        ProjectWorkerRemoveView.as_view(),
        name="project-worker-remove",
    ),
]
