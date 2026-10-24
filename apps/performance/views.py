"""Employee Performance API.

Admin-only CRUD lives under /api/v1/workers/{id}/performance/.
Workers will eventually see their own records through /api/v1/me/performance/
once ``is_visible_to_worker`` is true; the endpoint is already wired but only
returns records that the admin has flagged as visible.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ResourceNotFound
from apps.common.pagination import DefaultPagination
from apps.common.permissions import IsAdminRole
from apps.performance import services
from apps.performance.models import PerformanceRecord
from apps.performance.serializers import (
    PerformanceRecordSerializer,
    PerformanceRecordWriteSerializer,
)
from apps.workers.models import WorkerProfile


def _get_record_or_404(pk):
    try:
        return PerformanceRecord.objects.select_related("worker", "evaluator").get(pk=pk)
    except PerformanceRecord.DoesNotExist:
        raise ResourceNotFound(
            detail="Performance record does not exist.", code="PERFORMANCE_NOT_FOUND"
        )


class WorkerPerformanceListCreateView(APIView):
    """GET/POST /workers/{worker_id}/performance/"""

    permission_classes = [IsAdminRole]
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["period_end", "created_at"]

    def _get_worker(self, pk):
        try:
            return WorkerProfile.objects.get(pk=pk)
        except WorkerProfile.DoesNotExist:
            raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")

    def get(self, request, worker_id):
        worker = self._get_worker(worker_id)
        qs = PerformanceRecord.objects.filter(worker=worker).select_related(
            "worker", "evaluator"
        )
        ordering = request.query_params.get("ordering", "-period_end,-id")
        qs = qs.order_by(*[f for f in ordering.split(",") if f])
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = PerformanceRecordSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, worker_id):
        worker = self._get_worker(worker_id)
        serializer = PerformanceRecordWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        validated["worker"] = worker
        record = services.create_performance_record(actor=request.user, validated_data=validated)
        return Response(
            PerformanceRecordSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )


class WorkerPerformanceDetailView(APIView):
    """GET/PUT/PATCH/DELETE /workers/{worker_id}/performance/{record_id}/"""

    permission_classes = [IsAdminRole]

    def _get_record(self, worker_id, record_id):
        try:
            return PerformanceRecord.objects.select_related("worker", "evaluator").get(
                pk=record_id, worker_id=worker_id
            )
        except PerformanceRecord.DoesNotExist:
            raise ResourceNotFound(
                detail="Performance record does not exist.",
                code="PERFORMANCE_NOT_FOUND",
            )

    def get(self, request, worker_id, record_id):
        record = self._get_record(worker_id, record_id)
        return Response(PerformanceRecordSerializer(record).data)

    def put(self, request, worker_id, record_id):
        record = self._get_record(worker_id, record_id)
        serializer = PerformanceRecordWriteSerializer(record, data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_performance_record(
            actor=request.user,
            record=record,
            validated_data=dict(serializer.validated_data),
        )
        record.refresh_from_db()
        return Response(PerformanceRecordSerializer(record).data)

    def patch(self, request, worker_id, record_id):
        record = self._get_record(worker_id, record_id)
        serializer = PerformanceRecordWriteSerializer(record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_performance_record(
            actor=request.user,
            record=record,
            validated_data=dict(serializer.validated_data),
        )
        record.refresh_from_db()
        return Response(PerformanceRecordSerializer(record).data)

    def delete(self, request, worker_id, record_id):
        record = self._get_record(worker_id, record_id)
        services.delete_performance_record(actor=request.user, record=record)
        return Response(status=status.HTTP_204_NO_CONTENT)
