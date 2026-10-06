"""TBM & work-permit API.

Both the list and the write endpoints require ADMIN or a worker flagged as
`is_supervisor`. Supervisors only ever see or touch records on the projects
they are assigned to, and only for workers assigned to those projects; admins
are unrestricted. That mirrors the attendance module.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ResourceNotFound
from apps.common.pagination import DefaultPagination
from apps.common.permissions import IsAdminOrSupervisor, supervisor_profile
from apps.permits import services
from apps.permits.filters import WorkPermitFilter
from apps.permits.models import WorkPermit
from apps.permits.serializers import WorkPermitSerializer, WorkPermitWriteSerializer


class WorkPermitListCreateView(APIView):
    """GET/POST /permits/ - list or raise a TBM & work permit."""

    permission_classes = [IsAdminOrSupervisor]
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = WorkPermitFilter
    ordering_fields = ["date", "project_id", "worker_id", "created_at"]
    ordering = ["-date", "project_id", "worker_id"]
    # The two sheets make the payload multipart-only on write.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        supervisor = supervisor_profile(request.user)
        queryset = services.get_visible_permits(request.user, supervisor)
        queryset = self.filterset_class(request.GET, queryset=queryset).qs
        ordering = request.query_params.get("ordering")
        queryset = queryset.order_by(*(ordering.split(","))) if ordering else queryset

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = WorkPermitSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        supervisor = supervisor_profile(request.user)
        serializer = WorkPermitWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        record = services.create_permit(
            actor=request.user,
            supervisor=supervisor,
            project_id=validated.pop("project", None).pk if validated.get("project") else None,
            worker_id=validated.pop("worker", None).pk if validated.get("worker") else None,
            validated_data=validated,
        )
        return Response(
            WorkPermitSerializer(record, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class WorkPermitDetailView(APIView):
    """GET/PUT/PATCH/DELETE /permits/{id}/."""

    permission_classes = [IsAdminOrSupervisor]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _get(self, request, pk):
        supervisor = supervisor_profile(request.user)
        queryset = services.get_visible_permits(request.user, supervisor)
        try:
            return queryset.get(pk=pk)
        except WorkPermit.DoesNotExist:
            raise ResourceNotFound(detail="Work permit does not exist.", code="PERMIT_NOT_FOUND")

    def get(self, request, pk=None):
        record = self._get(request, pk)
        return Response(WorkPermitSerializer(record, context={"request": request}).data)

    def put(self, request, pk=None):
        return self._write(request, pk, partial=False)

    def patch(self, request, pk=None):
        return self._write(request, pk, partial=True)

    def _write(self, request, pk, *, partial):
        supervisor = supervisor_profile(request.user)
        record = self._get(request, pk)
        serializer = WorkPermitWriteSerializer(record, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updated = services.update_permit(
            actor=request.user,
            supervisor=supervisor,
            record=record,
            validated_data=dict(serializer.validated_data),
        )
        return Response(WorkPermitSerializer(updated, context={"request": request}).data)

    def delete(self, request, pk=None):
        # Only admins may remove permits; supervisors can add and correct.
        if not services.is_admin(request.user):
            raise PermissionDenied(detail="Only administrators can delete work permits.")
        record = self._get(request, pk)
        services.delete_permit(actor=request.user, record=record)
        return Response(status=status.HTTP_204_NO_CONTENT)
