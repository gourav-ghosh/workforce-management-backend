"""Project management API (admin only)."""

from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminRole
from apps.projects import services
from apps.projects.filters import ProjectFilter
from apps.projects.models import Project
from apps.projects.serializers import (
    ProjectDetailSerializer,
    ProjectListSerializer,
    ProjectWorkerAssignSerializer,
    ProjectWorkerSerializer,
    ProjectWriteSerializer,
)


class ProjectViewSet(ModelViewSet):
    """CRUD plus worker assignment endpoints for projects."""

    permission_classes = [IsAdminRole]
    queryset = Project.objects.all().annotate(
        active_workers_count=Count(
            "worker_assignments", filter=Q(worker_assignments__is_active=True)
        ),
    )
    filterset_class = ProjectFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["project_number", "project_name", "client_name", "location"]
    ordering_fields = [
        "project_number",
        "project_name",
        "status",
        "created_at",
        "start_date",
    ]

    def get_serializer_class(self):
        if self.action == "list":
            return ProjectListSerializer
        if self.action == "retrieve":
            return ProjectDetailSerializer
        return ProjectWriteSerializer

    def perform_destroy(self, instance):
        services.delete_project(actor=self.request.user, project=instance)

    @action(detail=True, methods=["get", "post"], url_path="workers")
    def workers(self, request, pk=None):
        """GET lists assignments; POST assigns a worker: {"worker_id": <id>}."""
        project = self.get_object()
        if request.method == "GET":
            assignments = project.worker_assignments.select_related(
                "worker", "worker__user"
            ).order_by("-assigned_at")
            page = self.paginate_queryset(assignments)
            serializer = ProjectWorkerSerializer(page, many=True)
            if page is not None:
                return self.get_paginated_response(serializer.data)
            return Response(ProjectWorkerSerializer(assignments, many=True).data)

        serializer = ProjectWorkerAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = services.assign_worker_to_project(
            actor=request.user,
            project=project,
            worker_id=serializer.validated_data["worker_id"],
        )
        return Response(ProjectWorkerSerializer(assignment).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"workers/(?P<worker_id>[^/.]+)",
    )
    def remove_worker(self, request, pk=None, worker_id=None):
        """DELETE /projects/{id}/workers/{worker_id}/ — unassigns the worker."""
        services.unassign_worker_from_project(
            actor=request.user,
            project=self.get_object(),
            worker_id=worker_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
