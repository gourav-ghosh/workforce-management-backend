"""PPE management API (admin only)."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminRole
from apps.ppe import services
from apps.ppe.filters import PPEFilter
from apps.ppe.models import PPE, PPEMedia
from apps.ppe.serializers import (
    PPEDetailSerializer,
    PPEHistorySerializer,
    PPEIssueSerializer,
    PPEListSerializer,
    PPEMediaSerializer,
    PPEMediaUploadSerializer,
    PPEReturnSerializer,
    PPEWriteSerializer,
)


class PPEViewSet(ModelViewSet):
    """PPE catalogue CRUD plus issue/return/history workflows."""

    permission_classes = [IsAdminRole]
    queryset = PPE.objects.all().prefetch_related("assignments__worker__user").order_by("ppe_id")
    filterset_class = PPEFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["ppe_id", "name", "ppe_type", "assignments__worker__full_name"]
    ordering_fields = ["ppe_id", "name", "status", "created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return PPEListSerializer
        if self.action == "retrieve":
            return PPEDetailSerializer
        return PPEWriteSerializer

    def perform_destroy(self, instance):
        services.delete_ppe(actor=self.request.user, ppe_item=instance)

    @action(
        detail=True,
        methods=["post"],
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def assign(self, request, pk=None):
        """POST /ppe/{id}/assign/ — issue PPE to a worker (multipart photos allowed)."""
        serializer = PPEIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        photos = data.pop("photos", [])
        worker_id = data.pop("worker_id")
        assignment = services.issue_ppe(
            actor=request.user,
            ppe_id=pk,
            worker_id=worker_id,
            media_files=photos,
            **data,
        )
        return Response(
            {
                "assignment_id": assignment.id,
                "ppe_id": pk,
                "worker_id": assignment.worker_id,
                "issue_date": assignment.issue_date,
                "expected_return_date": assignment.expected_return_date,
                "issue_condition": assignment.issue_condition,
                "status": assignment.status,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="return",
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def return_ppe_action(self, request, pk=None):
        """POST /ppe/{id}/return/ — record a PPE return."""
        serializer = PPEReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        photos = data.pop("photos", [])
        condition = data.pop("return_condition")
        assignment = services.return_ppe(
            actor=request.user,
            ppe_id=pk,
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
                "ppe_availability_status": PPE.objects.get(pk=pk).availability_status,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """GET /ppe/{id}/history/ — chronological assignment history."""
        ppe_item = self.get_object()
        assignments = ppe_item.assignments.select_related("worker", "worker__user")
        page = self.paginate_queryset(assignments)
        serializer = PPEHistorySerializer(page, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(PPEHistorySerializer(assignments, many=True).data)

    @action(
        detail=True,
        methods=["get", "post"],
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def media(self, request, pk=None):
        """GET/POST /ppe/{id}/media/ — photo gallery for the PPE item."""
        ppe_item = self.get_object()
        if request.method == "GET":
            items = ppe_item.media.select_related("assignment")
            page = self.paginate_queryset(items)
            serializer = PPEMediaSerializer(page, many=True)
            if page is not None:
                return self.get_paginated_response(serializer.data)
            return Response(PPEMediaSerializer(items, many=True).data)

        upload = PPEMediaUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        media_item = PPEMedia.objects.create(
            ppe=ppe_item,
            media_type=upload.validated_data.get("media_type", PPEMedia.MediaType.GENERAL),
            file=upload.validated_data["file"],
        )
        return Response(
            PPEMediaSerializer(media_item, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, pk=None):
        new_status = request.data.get("availability_status")
        valid = {choice for choice, _ in PPE.AvailabilityStatus.choices}
        if new_status not in valid:
            return Response(
                {"availability_status": ["Invalid status."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ppe_item = services.update_ppe_status(
            actor=request.user, ppe_item=self.get_object(), new_status=new_status
        )
        return Response({"availability_status": ppe_item.availability_status})
