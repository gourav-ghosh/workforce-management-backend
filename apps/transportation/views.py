"""Vehicle management API (admin only)."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminRole
from apps.transportation import services
from apps.transportation.filters import VehicleFilter
from apps.transportation.models import Vehicle, VehicleMedia
from apps.transportation.serializers import (
    VehicleAssignSerializer,
    VehicleDetailSerializer,
    VehicleHistorySerializer,
    VehicleListSerializer,
    VehicleMediaSerializer,
    VehicleMediaUploadSerializer,
    VehicleUnassignSerializer,
    VehicleWriteSerializer,
)


class VehicleViewSet(ModelViewSet):
    """Vehicle CRUD plus assign/unassign/history workflows."""

    permission_classes = [IsAdminRole]
    queryset = Vehicle.objects.all().order_by("vehicle_id")
    filterset_class = VehicleFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["vehicle_id", "registration_number", "make_model"]
    ordering_fields = ["vehicle_id", "registration_number", "status", "created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return VehicleListSerializer
        if self.action == "retrieve":
            return VehicleDetailSerializer
        return VehicleWriteSerializer

    def perform_destroy(self, instance):
        services.delete_vehicle(actor=self.request.user, vehicle=instance)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """POST /vehicles/{id}/assign/ — create an assignment."""
        serializer = VehicleAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = services.assign_vehicle(
            actor=request.user, vehicle_id=pk, **dict(serializer.validated_data)
        )
        return Response(
            {
                "assignment_id": assignment.id,
                "vehicle_id": pk,
                "assignment_type": assignment.assignment_type,
                "start_datetime": assignment.start_datetime,
                "end_datetime": assignment.end_datetime,
                "vehicle_status": assignment.vehicle.status,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="unassign")
    def unassign(self, request, pk=None):
        """POST /vehicles/{id}/unassign/ — close the open assignment."""
        serializer = VehicleUnassignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        assignment = services.unassign_vehicle(
            actor=request.user,
            vehicle_id=pk,
            assignment_id=data.get("assignment_id"),
            end_datetime=data.get("end_datetime"),
        )
        return Response(
            {
                "assignment_id": assignment.id,
                "end_datetime": assignment.end_datetime,
                "vehicle_status": Vehicle.objects.get(pk=pk).status,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """GET /vehicles/{id}/history/ — chronological usage history."""
        vehicle = self.get_object()
        assignments = vehicle.assignments.select_related("project", "worker", "driver")
        page = self.paginate_queryset(assignments)
        serializer = VehicleHistorySerializer(page, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(VehicleHistorySerializer(assignments, many=True).data)

    @action(
        detail=True,
        methods=["get", "post"],
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def media(self, request, pk=None):
        """GET/POST /vehicles/{id}/media/ — photo gallery."""
        vehicle = self.get_object()
        if request.method == "GET":
            items = vehicle.media.all()
            page = self.paginate_queryset(items)
            serializer = VehicleMediaSerializer(page, many=True)
            if page is not None:
                return self.get_paginated_response(serializer.data)
            return Response(VehicleMediaSerializer(items, many=True).data)

        upload = VehicleMediaUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        media_item = VehicleMedia.objects.create(
            vehicle=vehicle, file=upload.validated_data["file"]
        )
        return Response(
            VehicleMediaSerializer(media_item, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, pk=None):
        new_status = request.data.get("status")
        valid = {choice for choice, _ in Vehicle.Status.choices}
        if new_status not in valid:
            return Response({"status": ["Invalid status."]}, status=status.HTTP_400_BAD_REQUEST)
        vehicle = services.update_vehicle_status(
            actor=request.user, vehicle=self.get_object(), new_status=new_status
        )
        return Response({"status": vehicle.status})
