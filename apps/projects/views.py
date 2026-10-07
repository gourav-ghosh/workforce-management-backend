"""Project management API.

Writes are admin only. Reads of the project list and of a project's roster are
also available to supervisors, because marking attendance and raising a TBM /
work permit both require picking one of *their* projects and its workers. A
supervisor's reads are scoped to the projects they are assigned to.
"""

from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ResourceNotFound
from apps.common.pagination import DefaultPagination
from apps.common.permissions import IsAdminOrSupervisor, IsAdminRole, supervisor_profile
from apps.projects import services
from apps.projects.filters import ProjectFilter
from apps.projects.models import Project, ProjectWorker
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


def _supervised_project_ids(supervisor):
    """Projects the supervisor is currently assigned to."""
    if not supervisor:
        return set()
    return set(
        ProjectWorker.objects.filter(worker=supervisor, is_active=True).values_list(
            "project_id", flat=True
        )
    )


def _assert_supervisor_scope(supervisor, project):
    """Out-of-scope reads answer 404, matching attendance and permits."""
    if supervisor is None:
        return
    if project.pk not in _supervised_project_ids(supervisor):
        raise ResourceNotFound(detail="Project does not exist.", code="PROJECT_NOT_FOUND")


class ProjectListCreateView(APIView):
    """GET /projects/ — list projects; POST /projects/ — create a project."""

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

    def get_permissions(self):
        # Supervisors read the list to pick a project when marking attendance
        # or raising a permit; creating a project stays admin-only.
        if self.request.method == "GET":
            return [IsAdminOrSupervisor()]
        return [IsAdminRole()]

    def get(self, request):
        supervisor = supervisor_profile(request.user)
        queryset = Project.objects.all().annotate(
            active_workers_count=Count(
                "worker_assignments", filter=Q(worker_assignments__is_active=True)
            ),
        )
        if supervisor is not None:
            queryset = queryset.filter(id__in=_supervised_project_ids(supervisor))
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

    pagination_class = DefaultPagination
    serializer_class = ProjectWorkerSerializer

    def get_permissions(self):
        # Reading the roster is how a supervisor picks the workers they are
        # recording attendance / permits for. Assigning stays admin-only.
        if self.request.method == "GET":
            return [IsAdminOrSupervisor()]
        return [IsAdminRole()]

    def get(self, request, pk=None):
        supervisor = supervisor_profile(request.user)
        project = _get_project_or_404(pk)
        _assert_supervisor_scope(supervisor, project)
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
