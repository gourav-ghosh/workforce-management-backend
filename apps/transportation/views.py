"""Vehicle management API (admin only)."""

from django.utils import timezone
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
from apps.transportation import services
from apps.transportation.filters import VehicleFilter
from apps.transportation.models import (
    Vehicle,
    VehicleBooking,
    VehicleBookingStatus,
    VehicleMedia,
)
from apps.transportation.serializers import (
    VehicleAssignSerializer,
    VehicleBookingReadSerializer,
    VehicleBookingWriteSerializer,
    VehicleDetailSerializer,
    VehicleHistorySerializer,
    VehicleListSerializer,
    VehicleMediaSerializer,
    VehicleMediaUploadSerializer,
    VehicleUnassignSerializer,
    VehicleWriteSerializer,
)


def _get_vehicle_or_404(vehicle_id):
    """Look up a vehicle by its primary key when the value is an integer,
    otherwise by the `vehicle_id` business code.
    """
    lookup = {}
    if isinstance(vehicle_id, int) or (isinstance(vehicle_id, str) and vehicle_id.isdigit()):
        lookup["pk"] = int(vehicle_id)
    else:
        lookup["vehicle_id"] = vehicle_id
    try:
        return Vehicle.objects.get(**lookup)
    except Vehicle.DoesNotExist:
        raise ResourceNotFound(detail="Vehicle does not exist.", code="VEHICLE_NOT_FOUND")


class VehicleStockSummaryView(APIView):
    """GET /vehicles/stock/ — aggregated counts by status and type.

    Used by the stock-detail card on the vehicles list page and by the
    combined stock screen. `groups` is the vehicle-type breakdown, which is
    the category equivalent for transportation.
    """

    permission_classes = [IsAdminRole]

    def get(self, request):
        from django.db.models import Count

        qs = Vehicle.objects.all()
        by_status = dict(
            qs.values("status").annotate(count=Count("id")).values_list("status", "count")
        )
        by_type = dict(
            qs.values("vehicle_type")
            .annotate(count=Count("id"))
            .values_list("vehicle_type", "count")
        )
        return Response(
            {
                "total": qs.count(),
                "available": by_status.get(Vehicle.Status.AVAILABLE, 0),
                "in_use": by_status.get(Vehicle.Status.IN_USE, 0),
                "under_maintenance": by_status.get(Vehicle.Status.UNDER_MAINTENANCE, 0),
                "retired": by_status.get(Vehicle.Status.RETIRED, 0),
                "truck": by_type.get(Vehicle.VehicleType.TRUCK, 0),
                "van": by_type.get(Vehicle.VehicleType.VAN, 0),
                "pickup": by_type.get(Vehicle.VehicleType.PICKUP, 0),
                "car": by_type.get(Vehicle.VehicleType.CAR, 0),
                "bus": by_type.get(Vehicle.VehicleType.BUS, 0),
                "trailer": by_type.get(Vehicle.VehicleType.TRAILER, 0),
                "dumper": by_type.get(Vehicle.VehicleType.DUMPER, 0),
                "other": by_type.get(Vehicle.VehicleType.OTHER, 0),
                "groups": status_breakdown(
                    qs,
                    "vehicle_type",
                    "status",
                    dict(Vehicle.VehicleType.choices),
                    statuses=[s for s, _ in Vehicle.Status.choices],
                ),
            }
        )


class VehicleListCreateView(APIView):
    """GET /vehicles/ — list vehicles; POST /vehicles/ — create a vehicle."""

    permission_classes = [IsAdminRole]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = VehicleFilter
    search_fields = ["vehicle_id", "registration_number", "make_model"]
    ordering_fields = ["vehicle_id", "registration_number", "status", "created_at"]
    pagination_class = DefaultPagination

    def get(self, request):
        queryset = Vehicle.objects.all().order_by("vehicle_id")
        for backend in self.filter_backends:
            queryset = backend().filter_queryset(request, queryset, self)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = VehicleListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = VehicleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.save()
        return Response(
            VehicleDetailSerializer(vehicle, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class VehicleDetailView(APIView):
    """GET/PUT/PATCH/DELETE /vehicles/{id}/ — vehicle detail."""

    permission_classes = [IsAdminRole]

    def get(self, request, vehicle_id=None):
        vehicle = _get_vehicle_or_404(vehicle_id)
        return Response(VehicleDetailSerializer(vehicle, context={"request": request}).data)

    def put(self, request, vehicle_id=None):
        vehicle = _get_vehicle_or_404(vehicle_id)
        serializer = VehicleWriteSerializer(vehicle, data=request.data)
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.save()
        return Response(VehicleDetailSerializer(vehicle, context={"request": request}).data)

    def patch(self, request, vehicle_id=None):
        vehicle = _get_vehicle_or_404(vehicle_id)
        serializer = VehicleWriteSerializer(vehicle, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.save()
        return Response(VehicleDetailSerializer(vehicle, context={"request": request}).data)

    def delete(self, request, vehicle_id=None):
        vehicle = _get_vehicle_or_404(vehicle_id)
        services.delete_vehicle(actor=request.user, vehicle=vehicle)
        return Response(status=status.HTTP_204_NO_CONTENT)


class VehicleAssignView(APIView):
    """POST /vehicles/{id}/assign/ — create an assignment."""

    permission_classes = [IsAdminRole]

    def post(self, request, vehicle_id=None):
        _get_vehicle_or_404(vehicle_id)
        serializer = VehicleAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = services.assign_vehicle(
            actor=request.user, vehicle_id=vehicle_id, **dict(serializer.validated_data)
        )
        return Response(
            {
                "assignment_id": assignment.id,
                "vehicle_id": vehicle_id,
                "assignment_type": assignment.assignment_type,
                "start_datetime": assignment.start_datetime,
                "end_datetime": assignment.end_datetime,
                "vehicle_status": assignment.vehicle.status,
            },
            status=status.HTTP_201_CREATED,
        )


class VehicleUnassignView(APIView):
    """POST /vehicles/{id}/unassign/ — close the open assignment."""

    permission_classes = [IsAdminRole]

    def post(self, request, vehicle_id=None):
        _get_vehicle_or_404(vehicle_id)
        serializer = VehicleUnassignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        assignment = services.unassign_vehicle(
            actor=request.user,
            vehicle_id=vehicle_id,
            assignment_id=data.get("assignment_id"),
            end_datetime=data.get("end_datetime"),
        )
        return Response(
            {
                "assignment_id": assignment.id,
                "end_datetime": assignment.end_datetime,
                "vehicle_status": _get_vehicle_or_404(vehicle_id).status,
            },
            status=status.HTTP_200_OK,
        )


class VehicleHistoryView(APIView):
    """GET /vehicles/{id}/history/ — chronological usage history."""

    permission_classes = [IsAdminRole]
    pagination_class = DefaultPagination
    serializer_class = VehicleHistorySerializer

    def get(self, request, vehicle_id=None):
        vehicle = _get_vehicle_or_404(vehicle_id)
        qs = vehicle.assignments.select_related("project", "worker", "driver").order_by(
            "-start_datetime", "-id"
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = self.serializer_class(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class VehicleMediaView(APIView):
    """GET/POST /vehicles/{id}/media/ — photo gallery."""

    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = DefaultPagination
    serializer_class = VehicleMediaSerializer

    def get(self, request, vehicle_id=None):
        vehicle = _get_vehicle_or_404(vehicle_id)
        qs = vehicle.media.all().order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = self.serializer_class(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, vehicle_id=None):
        vehicle = _get_vehicle_or_404(vehicle_id)
        upload = VehicleMediaUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        media_item = VehicleMedia.objects.create(
            vehicle=vehicle, file=upload.validated_data["file"]
        )
        return Response(
            self.serializer_class(media_item, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class VehicleSetStatusView(APIView):
    """POST /vehicles/{id}/set-status/ {"status": ...}."""

    permission_classes = [IsAdminRole]

    def post(self, request, vehicle_id=None):
        new_status = request.data.get("status")
        valid = {choice for choice, _ in Vehicle.Status.choices}
        if new_status not in valid:
            return Response({"status": ["Invalid status."]}, status=status.HTTP_400_BAD_REQUEST)
        vehicle = _get_vehicle_or_404(vehicle_id)
        vehicle = services.update_vehicle_status(
            actor=request.user, vehicle=vehicle, new_status=new_status
        )
        return Response({"status": vehicle.status})


class VehicleBookingListCreateView(APIView):
    """GET /vehicles/{id}/bookings/ — list bookings for a vehicle (admin).

    POST /vehicles/{id}/bookings/ — create a new future booking.
    """

    permission_classes = [IsAdminRole]

    def get(self, request, vehicle_id=None):
        vehicle = _get_vehicle_or_404(vehicle_id)
        qs = VehicleBooking.objects.filter(vehicle=vehicle).select_related(
            "driver", "project", "worker", "booked_by"
        )
        start_after = request.query_params.get("start_after")
        if start_after:
            qs = qs.filter(start_datetime__gte=start_after)
        end_before = request.query_params.get("end_before")
        if end_before:
            qs = qs.filter(end_datetime__lte=end_before)
        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        qs = qs.order_by("start_datetime")
        return Response(
            VehicleBookingReadSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request, vehicle_id=None):
        vehicle = _get_vehicle_or_404(vehicle_id)
        serializer = VehicleBookingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = services.create_vehicle_booking(
            actor=request.user, vehicle=vehicle, validated_data=dict(serializer.validated_data)
        )
        return Response(
            VehicleBookingReadSerializer(booking, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class VehicleBookingDetailView(APIView):
    """GET/PUT/PATCH/DELETE /vehicles/{vehicle_id}/bookings/{booking_id}/."""

    permission_classes = [IsAdminRole]

    def get(self, request, vehicle_id=None, booking_id=None):
        booking = _get_booking_or_404(vehicle_id, booking_id)
        return Response(VehicleBookingReadSerializer(booking, context={"request": request}).data)

    def put(self, request, vehicle_id=None, booking_id=None):
        booking = _get_booking_or_404(vehicle_id, booking_id)
        serializer = VehicleBookingWriteSerializer(booking, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        booking = services.update_vehicle_booking(
            booking=booking, validated_data=dict(serializer.validated_data)
        )
        return Response(VehicleBookingReadSerializer(booking, context={"request": request}).data)

    def patch(self, request, vehicle_id=None, booking_id=None):
        booking = _get_booking_or_404(vehicle_id, booking_id)
        serializer = VehicleBookingWriteSerializer(booking, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        booking = services.update_vehicle_booking(
            booking=booking, validated_data=dict(serializer.validated_data)
        )
        return Response(VehicleBookingReadSerializer(booking, context={"request": request}).data)

    def delete(self, request, vehicle_id=None, booking_id=None):
        booking = _get_booking_or_404(vehicle_id, booking_id)
        services.delete_vehicle_booking(actor=request.user, booking=booking)
        return Response(status=status.HTTP_204_NO_CONTENT)


class VehicleBookingCalendarView(APIView):
    """GET /bookings/ — list all upcoming bookings across the fleet.

    Supports start_after and end_before query params for date-range
    filtering. Used by the admin calendar / dashboard widget.
    """

    permission_classes = [IsAdminRole]

    def get(self, request):
        qs = VehicleBooking.objects.select_related(
            "vehicle", "driver", "project", "worker", "booked_by"
        )
        qs = qs.filter(start_datetime__gte=timezone.now())
        start_after = request.query_params.get("start_after")
        if start_after:
            qs = qs.filter(start_datetime__gte=start_after)
        end_before = request.query_params.get("end_before")
        if end_before:
            qs = qs.filter(end_datetime__lte=end_before)
        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        qs = qs.exclude(status=VehicleBookingStatus.CANCELLED).order_by("start_datetime")
        return Response(
            VehicleBookingReadSerializer(qs, many=True, context={"request": request}).data
        )


def _get_booking_or_404(vehicle_id, booking_id):
    vehicle = _get_vehicle_or_404(vehicle_id)
    try:
        return VehicleBooking.objects.select_related(
            "vehicle", "driver", "project", "worker", "booked_by"
        ).get(vehicle=vehicle, pk=booking_id)
    except VehicleBooking.DoesNotExist:
        raise ResourceNotFound(detail="Vehicle booking does not exist.", code="BOOKING_NOT_FOUND")
