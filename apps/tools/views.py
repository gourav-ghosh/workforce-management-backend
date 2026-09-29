"""Tool management API (admin only)."""

from django.db.models import Count, Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ResourceNotFound
from apps.common.pagination import DefaultPagination
from apps.common.permissions import IsAdminRole
from apps.common.stock import status_breakdown
from apps.tools import services
from apps.tools.filters import ToolFilter
from apps.tools.models import Tool, ToolMedia
from apps.tools.serializers import (
    ToolDamageInputSerializer,
    ToolDamageReadSerializer,
    ToolDetailSerializer,
    ToolHistorySerializer,
    ToolIssueSerializer,
    ToolListSerializer,
    ToolMediaSerializer,
    ToolMediaUploadSerializer,
    ToolReturnSerializer,
    ToolWriteSerializer,
)


def _get_tool_or_404(pk):
    try:
        return Tool.objects.get(pk=pk)
    except Tool.DoesNotExist:
        raise ResourceNotFound(detail="Tool does not exist.", code="TOOL_NOT_FOUND")


class ToolStockSummaryView(APIView):
    """GET /tools/stock/ — aggregated counts by status and category.

    Used by the stock-detail card on the tools list page and by the combined
    stock screen. `groups` is the category-wise breakdown (uncategorised tools
    are reported as "Uncategorised" rather than dropped).
    """

    permission_classes = [IsAdminRole]

    def get(self, request):
        qs = Tool.objects.all()
        rows = qs.values("availability_status").annotate(count=Count("id"))
        by_status = {row["availability_status"]: row["count"] for row in rows}
        return Response(
            {
                "total": qs.count(),
                "available": by_status.get(Tool.AvailabilityStatus.AVAILABLE, 0),
                "assigned": by_status.get(Tool.AvailabilityStatus.ASSIGNED, 0),
                "damaged": by_status.get(Tool.AvailabilityStatus.DAMAGED, 0),
                "under_maintenance": by_status.get(Tool.AvailabilityStatus.UNDER_MAINTENANCE, 0),
                "lost": by_status.get(Tool.AvailabilityStatus.LOST, 0),
                "retired": by_status.get(Tool.AvailabilityStatus.RETIRED, 0),
                "groups": status_breakdown(
                    qs,
                    "category",
                    "availability_status",
                    statuses=[s for s, _ in Tool.AvailabilityStatus.choices],
                ),
            }
        )


class ToolListCreateView(APIView):
    """GET /tools/ — list tools; POST /tools/ — create a tool."""

    permission_classes = [IsAdminRole]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ToolFilter
    search_fields = ["tool_id", "name", "category", "assignments__worker__full_name"]
    ordering_fields = ["tool_id", "name", "availability_status", "created_at"]
    pagination_class = DefaultPagination

    def get(self, request):
        queryset = (
            Tool.objects.all()
            .prefetch_related("assignments__worker__user", "damages")
            .order_by("tool_id")
        )
        for backend in self.filter_backends:
            queryset = backend().filter_queryset(request, queryset, self)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = ToolListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = ToolWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tool = serializer.save()
        return Response(
            ToolDetailSerializer(tool, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ToolDetailView(APIView):
    """GET/PUT/PATCH/DELETE /tools/{id}/ — tool detail."""

    permission_classes = [IsAdminRole]

    def get(self, request, pk=None):
        tool = _get_tool_or_404(pk)
        return Response(ToolDetailSerializer(tool, context={"request": request}).data)

    def put(self, request, pk=None):
        tool = _get_tool_or_404(pk)
        serializer = ToolWriteSerializer(tool, data=request.data)
        serializer.is_valid(raise_exception=True)
        tool = serializer.save()
        return Response(ToolDetailSerializer(tool, context={"request": request}).data)

    def patch(self, request, pk=None):
        tool = _get_tool_or_404(pk)
        serializer = ToolWriteSerializer(tool, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tool = serializer.save()
        return Response(ToolDetailSerializer(tool, context={"request": request}).data)

    def delete(self, request, pk=None):
        tool = _get_tool_or_404(pk)
        services.delete_tool(actor=request.user, tool=tool)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ToolIssueView(APIView):
    """POST /tools/{id}/issue/ — issue a tool to a worker (multipart photos allowed)."""

    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk=None):
        serializer = ToolIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        worker_id = data.pop("worker_id")
        project_id = data.pop("project_id", None)
        photos = data.pop("photos", [])
        assignment = services.issue_tool(
            actor=request.user,
            tool_id=pk,
            worker_id=worker_id,
            project_id=project_id,
            media_files=photos,
            **data,
        )
        out = {
            "assignment_id": assignment.id,
            "tool_id": pk,
            "worker_id": assignment.worker_id,
            "project_id": assignment.project_id,
            "issue_date": assignment.issue_date,
            "expected_return_date": assignment.expected_return_date,
            "issue_condition": assignment.issue_condition,
            "status": assignment.status,
        }
        return Response(out, status=status.HTTP_201_CREATED)


class ToolReturnView(APIView):
    """POST /tools/{id}/return/ — record a return (multipart photos allowed)."""

    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk=None):
        serializer = ToolReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        photos = data.pop("photos", [])
        condition = data.pop("return_condition")
        assignment = services.return_tool(
            actor=request.user,
            tool_id=pk,
            return_condition=condition,
            media_files=photos,
            **data,
        )
        return Response(
            {
                "assignment_id": assignment.id,
                "status": assignment.status,
                "return_date": assignment.return_date,
                "return_condition": assignment.return_condition,
                "tool_availability_status": Tool.objects.get(pk=pk).availability_status,
            },
            status=status.HTTP_200_OK,
        )


class ToolDamageView(APIView):
    """POST /tools/{id}/damage/ — record damage (multipart photos allowed)."""

    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk=None):
        serializer = ToolDamageInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        photos = data.pop("photos", [])
        damage_record = services.record_tool_damage(
            actor=request.user, tool_id=pk, media_files=photos, **data
        )
        return Response(
            ToolDamageReadSerializer(damage_record, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ToolHistoryView(APIView):
    """GET /tools/{id}/history/ — chronological assignment history with damage."""

    permission_classes = [IsAdminRole]
    pagination_class = DefaultPagination
    serializer_class = ToolHistorySerializer

    def get(self, request, pk=None):
        tool = _get_tool_or_404(pk)
        queryset = (
            tool.assignments.select_related("worker", "worker__user", "project")
            .prefetch_related(
                Prefetch("damages__media", queryset=ToolMedia.objects.all()),
                Prefetch("media", queryset=ToolMedia.objects.all()),
            )
            .order_by("-issue_date", "-id")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = self.serializer_class(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class ToolMediaView(APIView):
    """GET/POST /tools/{id}/media/ — photo gallery for the tool."""

    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = DefaultPagination

    def get(self, request, pk=None):
        tool = _get_tool_or_404(pk)
        qs = tool.media.select_related("assignment", "damage").order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ToolMediaSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, pk=None):
        tool = _get_tool_or_404(pk)
        upload = ToolMediaUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        media_item = ToolMedia.objects.create(
            tool=tool,
            media_type=upload.validated_data.get("media_type", ToolMedia.MediaType.GENERAL),
            file=upload.validated_data["file"],
        )
        return Response(
            ToolMediaSerializer(media_item, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ToolSetStatusView(APIView):
    """POST /tools/{id}/set-status/ {"availability_status": ...} — manual transitions."""

    permission_classes = [IsAdminRole]

    def post(self, request, pk=None):
        new_status = request.data.get("availability_status")
        valid = {choice for choice, _ in Tool.AvailabilityStatus.choices}
        if new_status not in valid:
            return Response(
                {"availability_status": ["Invalid status."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tool = _get_tool_or_404(pk)
        tool = services.update_tool_status(actor=request.user, tool=tool, new_status=new_status)
        return Response({"availability_status": tool.availability_status})


class ToolRepairView(APIView):
    """POST /tools/{id}/repair/ — close damage records and return to circulation.

    Body:
    {
      "condition": "GOOD",
      "close_assignment": true,        # optional, default true
      "notes": "..."                   # optional
    }
    """

    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk=None):
        condition = request.data.get("condition", Tool.Condition.GOOD)
        close = request.data.get("close_assignment", True)
        if isinstance(close, str):
            close = close.strip().lower() in {"true", "1", "yes", "on"}
        notes = request.data.get("notes", "")

        tool = _get_tool_or_404(pk)
        tool = services.repair_tool(
            actor=request.user,
            tool=tool,
            condition=condition,
            close_assignment=bool(close),
            notes=notes,
        )
        return Response(ToolDetailSerializer(tool, context={"request": request}).data)
