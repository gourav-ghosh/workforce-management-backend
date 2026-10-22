"""TBM & work-permit API.

The list, the summary and the write endpoints require ADMIN or a worker flagged
as `is_supervisor`. Supervisors only ever see or touch records on the projects
they are assigned to, and only for workers assigned to those projects; admins
are unrestricted. That mirrors the attendance module.
"""

from datetime import date

from django.db.models import Count
from django.db.models.functions import TruncMonth
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
from apps.permits.models import WorkPermit, today_in_permits_tz
from apps.permits.serializers import WorkPermitSerializer, WorkPermitWriteSerializer
from apps.workers.models import WorkerProfile

DEFAULT_SUMMARY_MONTHS = 3
MAX_SUMMARY_MONTHS = 24


class WorkPermitListCreateView(APIView):
    """GET/POST /permits/ - list or raise a TBM & work permit."""

    permission_classes = [IsAdminOrSupervisor]
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = WorkPermitFilter
    ordering_fields = ["date", "project_id", "id", "created_at"]
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
        workers = validated.pop("workers", [])
        project = validated.pop("project", None)
        record = services.create_permit(
            actor=request.user,
            supervisor=supervisor,
            project_id=project.pk if project is not None else None,
            workers=workers,
            validated_data=validated,
        )
        return Response(
            WorkPermitSerializer(record, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class WorkPermitMonthlySummaryView(APIView):
    """GET /permits/summary/ - month-wise permit and manpower counts.

    Backs the supervisor's home screen and the admin's view of a supervisor,
    which show how many permits were raised and how much manpower they
    covered, for the current month and the preceding ones.

    `manpower` is the total number of persons marked across the permits raised
    in that month, i.e. the sum of every permit's worker count. It is a
    person-per-permit total on purpose: a crew of 20 on one permit is 20
    manpower, and someone covered by three permits contributes 3. This is the
    figure the module reports; a distinct headcount is deliberately *not*
    offered, because it understates the manpower actually deployed.

    Months are returned newest first and always include months with no permits
    (as zeroes) so the client can render a stable list.

    Pass `?supervisor=<worker profile id>` to narrow the totals to a single
    supervisor's own projects, which is how the admin's worker-profile screen
    reports a per-supervisor panel.
    """

    permission_classes = [IsAdminOrSupervisor]

    def get(self, request):
        supervisor = supervisor_profile(request.user)
        months = _requested_months(request)

        queryset = services.get_visible_permits(request.user, supervisor)
        queryset = _scoped_to_supervisor(request, queryset)
        rows = (
            queryset.annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(
                permits=Count("id", distinct=True),
                # distinct=False so every worker row across the month's permits
                # is counted, giving the total manpower rather than a headcount.
                manpower=Count("workers", distinct=False),
            )
            .order_by("-month")
        )
        totals = {row["month"]: row for row in rows}

        data = [
            {
                "month": month.strftime("%Y-%m"),
                "label": month.strftime("%B %Y"),
                "permit_count": totals.get(month, {}).get("permits", 0),
                "manpower": totals.get(month, {}).get("manpower", 0),
                "is_current": month == today_in_permits_tz().replace(day=1),
            }
            for month in months
        ]
        return Response({"months": data, "month_count": len(data)})


def _scoped_to_supervisor(request, queryset):
    """Restrict to one supervisor's own projects via `?supervisor=<worker id>`.

    This is what the admin's worker-profile screen uses to show the metrics for
    an individual supervisor. Without it an admin only ever sees the whole
    company, which is not what a per-supervisor panel should show.
    """
    raw = request.query_params.get("supervisor")
    if not raw:
        return queryset
    try:
        profile = WorkerProfile.objects.get(pk=raw)
    except (WorkerProfile.DoesNotExist, ValueError, TypeError):
        raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")
    return queryset.filter(project_id__in=services.supervised_project_ids(profile))


def _requested_months(request):
    """The current month plus the N preceding ones, newest first."""
    try:
        months = int(request.query_params.get("months", DEFAULT_SUMMARY_MONTHS))
    except (TypeError, ValueError):
        months = DEFAULT_SUMMARY_MONTHS
    months = max(1, min(months, MAX_SUMMARY_MONTHS))

    current = today_in_permits_tz().replace(day=1)
    # month arithmetic via date, so year boundaries roll correctly.
    return [
        date(
            current.year + (current.month - 1 - offset) // 12,
            (current.month - 1 - offset) % 12 + 1,
            1,
        )
        for offset in range(months)
    ]


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
