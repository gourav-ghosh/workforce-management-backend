"""Attendance API.

Both the list and the write endpoints require ADMIN or a worker flagged as
`is_supervisor`. Supervisors only ever see or touch records on the projects
they are assigned to; admins are unrestricted.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attendance import services
from apps.attendance.filters import AttendanceFilter
from apps.attendance.models import AttendanceRecord
from apps.attendance.serializers import (
    AttendanceRecordSerializer,
    AttendanceRecordWriteSerializer,
)
from apps.common.exceptions import ResourceNotFound
from apps.common.pagination import DefaultPagination
from apps.common.permissions import IsAdminOrSupervisor, supervisor_profile


class AttendanceListCreateView(APIView):
    """GET/POST /attendance/ — list or mark attendance."""

    permission_classes = [IsAdminOrSupervisor]
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AttendanceFilter
    ordering_fields = ["date", "punch_in", "worker_id", "project_id"]
    ordering = ["-date", "worker_id"]

    def get(self, request):
        supervisor = supervisor_profile(request.user)
        queryset = services.get_visible_records(request.user, supervisor)
        queryset = self.filterset_class(request.GET, queryset=queryset).qs
        ordering = request.query_params.get("ordering")
        queryset = queryset.order_by(*(ordering.split(","))) if ordering else queryset

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = AttendanceRecordSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        supervisor = supervisor_profile(request.user)
        serializer = AttendanceRecordWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = services.mark_attendance(
            actor=request.user,
            supervisor=supervisor,
            worker_id=serializer.validated_data["worker"].pk,
            project_id=(
                serializer.validated_data["project"].pk
                if serializer.validated_data.get("project")
                else None
            ),
            validated_data=serializer.validated_data,
        )
        return Response(
            AttendanceRecordSerializer(record, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class AttendanceDetailView(APIView):
    """GET/PUT/PATCH/DELETE /attendance/{id}/."""

    permission_classes = [IsAdminOrSupervisor]

    def _get(self, request, pk):
        supervisor = supervisor_profile(request.user)
        queryset = services.get_visible_records(request.user, supervisor)
        try:
            return queryset.get(pk=pk)
        except AttendanceRecord.DoesNotExist:
            raise ResourceNotFound(
                detail="Attendance record does not exist.", code="ATTENDANCE_NOT_FOUND"
            )

    def get(self, request, pk=None):
        record = self._get(request, pk)
        return Response(AttendanceRecordSerializer(record, context={"request": request}).data)

    def put(self, request, pk=None):
        return self._write(request, pk, partial=False)

    def patch(self, request, pk=None):
        return self._write(request, pk, partial=True)

    def _write(self, request, pk, *, partial):
        supervisor = supervisor_profile(request.user)
        record = self._get(request, pk)
        serializer = AttendanceRecordWriteSerializer(record, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        updated = services.update_attendance(
            actor=request.user,
            supervisor=supervisor,
            record=record,
            validated_data=validated,
        )
        return Response(AttendanceRecordSerializer(updated, context={"request": request}).data)

    def delete(self, request, pk=None):
        # Only admins may remove attendance; supervisors can add and correct.
        if not services.is_admin(request.user):
            raise PermissionDenied(detail="Only administrators can delete attendance records.")
        record = self._get(request, pk)
        services.delete_attendance(actor=request.user, record=record)
        return Response(status=status.HTTP_204_NO_CONTENT)
