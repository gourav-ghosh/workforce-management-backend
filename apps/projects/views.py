"""Project management API (admin only)."""

from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ResourceNotFound
from apps.common.pagination import DefaultPagination
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


def _get_project_or_404(pk):
    try:
        return Project.objects.annotate(
            active_workers_count=Count(
                "worker_assignments", filter=Q(worker_assignments__is_active=True)
            ),
        ).get(pk=pk)
    except Project.DoesNotExist:
        raise ResourceNotFound(detail="Project does not exist.", code="PROJECT_NOT_FOUND")


class ProjectListCreateView(APIView):
    """GET /projects/ — list projects; POST /projects/ — create a project."""

    permission_classes = [IsAdminRole]
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProjectFilter
    search_fields = ["project_number", "project_name", "client_name", "location"]
    ordering_fields = [
        "project_number",
        "project_name",
        "status",
        "created_at",
        "start_date",
    ]

    def get(self, request):
        queryset = Project.objects.all().annotate(
            active_workers_count=Count(
                "worker_assignments", filter=Q(worker_assignments__is_active=True)
            ),
        )
        for backend in self.filter_backends:
            queryset = backend().filter_queryset(request, queryset, self)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = ProjectListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = ProjectWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        return Response(
            ProjectDetailSerializer(project, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectDetailView(APIView):
    """GET/PUT/PATCH/DELETE /projects/{id}/ — project detail."""

    permission_classes = [IsAdminRole]

    def get(self, request, pk=None):
        project = _get_project_or_404(pk)
        return Response(ProjectDetailSerializer(project, context={"request": request}).data)

    def put(self, request, pk=None):
        project = _get_project_or_404(pk)
        serializer = ProjectWriteSerializer(project, data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        return Response(ProjectDetailSerializer(project, context={"request": request}).data)

    def patch(self, request, pk=None):
        project = _get_project_or_404(pk)
        serializer = ProjectWriteSerializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        return Response(ProjectDetailSerializer(project, context={"request": request}).data)

    def delete(self, request, pk=None):
        project = _get_project_or_404(pk)
        services.delete_project(actor=request.user, project=project)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectWorkerListView(APIView):
    """GET/POST /projects/{id}/workers/ — list or assign workers."""

    permission_classes = [IsAdminRole]
    pagination_class = DefaultPagination
    serializer_class = ProjectWorkerSerializer

    def get(self, request, pk=None):
        project = _get_project_or_404(pk)
        qs = project.worker_assignments.select_related("worker", "worker__user").order_by(
            "-assigned_at"
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = self.serializer_class(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, pk=None):
        project = _get_project_or_404(pk)
        serializer = ProjectWorkerAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = services.assign_worker_to_project(
            actor=request.user,
            project=project,
            worker_id=serializer.validated_data["worker_id"],
        )
        return Response(
            ProjectWorkerSerializer(assignment, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectWorkerRemoveView(APIView):
    """DELETE /projects/{id}/workers/{worker_id}/ — unassigns the worker."""

    permission_classes = [IsAdminRole]

    def delete(self, request, pk=None, worker_id=None):
        project = _get_project_or_404(pk)
        services.unassign_worker_from_project(
            actor=request.user,
            project=project,
            worker_id=worker_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
