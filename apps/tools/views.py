"""Tool management API (admin only)."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminRole
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


class ToolViewSet(ModelViewSet):
    """Tool catalogue CRUD plus issue/return/damage/history workflows."""

    permission_classes = [IsAdminRole]
    queryset = (
        Tool.objects.all()
        .prefetch_related("assignments__worker__user", "damages")
        .order_by("tool_id")
    )
    filterset_class = ToolFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["tool_id", "name", "category", "assignments__worker__full_name"]
    ordering_fields = ["tool_id", "name", "status", "created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return ToolListSerializer
        if self.action == "retrieve":
            return ToolDetailSerializer
        return ToolWriteSerializer

    def perform_destroy(self, instance):
        services.delete_tool(actor=self.request.user, tool=instance)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """POST /tools/{id}/assign/ — issue the tool to a worker."""
        serializer = ToolIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        worker_id = data.pop("worker_id")
        project_id = data.pop("project_id", None)
        assignment = services.issue_tool(
            actor=request.user,
            tool_id=pk,
            worker_id=worker_id,
            project_id=project_id,
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

    @action(
        detail=True,
        methods=["post"],
        url_path="return",
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def return_tool(self, request, pk=None):
        """POST /tools/{id}/return/ — record a return (multipart photos allowed)."""
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

    @action(
        detail=True,
        methods=["post"],
        url_path="damage",
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def damage(self, request, pk=None):
        """POST /tools/{id}/damage/ — record damage (multipart photos allowed)."""
        serializer = ToolDamageInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        photos = data.pop("photos", [])
        damage_record = services.record_tool_damage(
            actor=request.user, tool_id=pk, media_files=photos, **data
        )
        return Response(
            ToolDamageReadSerializer(damage_record).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """GET /tools/{id}/history/ — chronological assignment history."""
        tool = self.get_object()
        assignments = tool.assignments.select_related(
            "worker", "worker__user", "project"
        ).prefetch_related("damages")
        page = self.paginate_queryset(assignments)
        serializer = ToolHistorySerializer(page, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(ToolHistorySerializer(assignments, many=True).data)

    @action(
        detail=True,
        methods=["get", "post"],
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def media(self, request, pk=None):
        """GET/POST /tools/{id}/media/ — photo gallery for the tool."""
        tool = self.get_object()
        if request.method == "GET":
            items = tool.media.select_related("assignment", "damage")
            page = self.paginate_queryset(items)
            serializer = ToolMediaSerializer(page, many=True)
            if page is not None:
                return self.get_paginated_response(serializer.data)
            return Response(ToolMediaSerializer(items, many=True).data)

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

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, pk=None):
        """POST /tools/{id}/set-status/ {"availability_status": ...} — manual transitions."""
        new_status = request.data.get("availability_status")
        valid = {choice for choice, _ in Tool.AvailabilityStatus.choices}
        if new_status not in valid:
            return Response(
                {"availability_status": ["Invalid status."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tool = services.update_tool_status(
            actor=request.user, tool=self.get_object(), new_status=new_status
        )
        return Response({"availability_status": tool.availability_status})
