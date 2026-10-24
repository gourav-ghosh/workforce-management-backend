"""PPE management API (admin only)."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ResourceNotFound
from apps.common.pagination import DefaultPagination
from apps.common.permissions import IsAdminRole
from apps.common.stock import status_breakdown, status_breakdown_by
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


def _get_ppe_or_404(pk):
    try:
        return PPE.objects.get(pk=pk)
    except PPE.DoesNotExist:
        raise ResourceNotFound(detail="PPE item does not exist.", code="PPE_NOT_FOUND")


class PPEStockSummaryView(APIView):
    """GET /ppe/stock/ - aggregated counts by status, condition, type and size.

    Used by the stock-detail card on the PPE list page and by the combined
    stock screen. PPE is tracked along type, size and a free-text category:

    - ``groups``         - by PPE type, with the size split nested inside each
                           type under ``sub_groups``, because the useful
                           question is "of the 20 safety shoes, how many are
                           size 7" rather than a fleet-wide size tally
    - ``size_groups``    - the overall size rollup across every type
    - ``category_groups`` - by the free-text category

    Blank values are reported as "Uncategorised" so the group counts always add
    up to the total.
    """

    permission_classes = [IsAdminRole]

    def get(self, request):
        from django.db.models import Sum

        qs = PPE.objects.all()
        total = qs.aggregate(total=Sum('total_quantity'))['total'] or 0
        available = qs.aggregate(available=Sum('available_quantity'))['available'] or 0
        assigned = total - available
        by_status = {}
        by_condition = {}
        for p in qs:
            by_status[p.availability_status] = by_status.get(p.availability_status, 0) + p.total_quantity
            by_condition[p.condition] = by_condition.get(p.condition, 0) + p.total_quantity
        return Response(
            {
                "total": total,
                "available": available,
                "assigned": assigned,
                "expired": by_status.get(PPE.AvailabilityStatus.EXPIRED, 0),
                "damaged": by_status.get(PPE.AvailabilityStatus.DAMAGED, 0),
                "retired": by_status.get(PPE.AvailabilityStatus.RETIRED, 0),
                "condition_good": by_condition.get(PPE.Condition.GOOD, 0),
                "condition_fair": by_condition.get(PPE.Condition.FAIR, 0),
                "condition_poor": by_condition.get(PPE.Condition.POOR, 0),
                "condition_damaged": by_condition.get(PPE.Condition.DAMAGED, 0),
                "groups": status_breakdown_by(
                    qs,
                    "ppe_type",
                    "size",
                    "availability_status",
                    outer_labels=dict(PPE.PPEType.choices),
                    statuses=[s for s, _ in PPE.AvailabilityStatus.choices],
                ),
                "size_groups": status_breakdown(
                    qs,
                    "size",
                    "availability_status",
                    statuses=[s for s, _ in PPE.AvailabilityStatus.choices],
                ),
                "category_groups": status_breakdown(
                    qs,
                    "category",
                    "availability_status",
                    statuses=[s for s, _ in PPE.AvailabilityStatus.choices],
                ),
            }
        )


class PPEListCreateView(APIView):
    """GET /ppe/ â€” list PPE; POST /ppe/ â€” create a PPE item."""

    permission_classes = [IsAdminRole]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PPEFilter
    search_fields = ["ppe_id", "name", "ppe_type", "assignments__worker__full_name"]
    ordering_fields = ["ppe_id", "name", "availability_status", "created_at"]
    pagination_class = DefaultPagination

    def get(self, request):
        queryset = (
            PPE.objects.all().prefetch_related("assignments__worker__user").order_by("ppe_id")
        )
        for backend in self.filter_backends:
            queryset = backend().filter_queryset(request, queryset, self)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = PPEListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = PPEWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ppe_item = serializer.save()
        return Response(
            PPEDetailSerializer(ppe_item, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class PPEDetailView(APIView):
    """GET/PUT/PATCH/DELETE /ppe/{id}/ â€” PPE detail."""

    permission_classes = [IsAdminRole]

    def get(self, request, pk=None):
        ppe_item = _get_ppe_or_404(pk)
        return Response(PPEDetailSerializer(ppe_item, context={"request": request}).data)

    def put(self, request, pk=None):
        ppe_item = _get_ppe_or_404(pk)
        serializer = PPEWriteSerializer(ppe_item, data=request.data)
        serializer.is_valid(raise_exception=True)
        ppe_item = serializer.save()
        return Response(PPEDetailSerializer(ppe_item, context={"request": request}).data)

    def patch(self, request, pk=None):
        ppe_item = _get_ppe_or_404(pk)
        serializer = PPEWriteSerializer(ppe_item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        ppe_item = serializer.save()
        return Response(PPEDetailSerializer(ppe_item, context={"request": request}).data)

    def delete(self, request, pk=None):
        ppe_item = _get_ppe_or_404(pk)
        services.delete_ppe(actor=request.user, ppe_item=ppe_item)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PPEIssueView(APIView):
    """POST /ppe/{id}/issue/ â€” issue PPE to a worker (multipart photos allowed)."""

    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk=None):
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


class PPEReturnView(APIView):
    """POST /ppe/{id}/return/ â€” record a PPE return."""

    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk=None):
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


class PPEHistoryView(APIView):
    """GET /ppe/{id}/history/ â€” chronological assignment history."""

    permission_classes = [IsAdminRole]
    pagination_class = DefaultPagination
    serializer_class = PPEHistorySerializer

    def get(self, request, pk=None):
        ppe_item = _get_ppe_or_404(pk)
        qs = ppe_item.assignments.select_related("worker", "worker__user").order_by(
            "-issue_date", "-id"
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = self.serializer_class(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class PPEMediaView(APIView):
    """GET/POST /ppe/{id}/media/ â€” photo gallery for the PPE item."""

    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = DefaultPagination
    serializer_class = PPEMediaSerializer

    def get(self, request, pk=None):
        ppe_item = _get_ppe_or_404(pk)
        qs = ppe_item.media.select_related("assignment").order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = self.serializer_class(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, pk=None):
        ppe_item = _get_ppe_or_404(pk)
        upload = PPEMediaUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        media_item = PPEMedia.objects.create(
            ppe=ppe_item,
            media_type=upload.validated_data.get("media_type", PPEMedia.MediaType.GENERAL),
            file=upload.validated_data["file"],
        )
        return Response(
            self.serializer_class(media_item, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class PPESetStatusView(APIView):
    """POST /ppe/{id}/set-status/ {"availability_status": ...}."""

    permission_classes = [IsAdminRole]

    def post(self, request, pk=None):
        new_status = request.data.get("availability_status")
        valid = {choice for choice, _ in PPE.AvailabilityStatus.choices}
        if new_status not in valid:
            return Response(
                {"availability_status": ["Invalid status."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ppe_item = _get_ppe_or_404(pk)
        ppe_item = services.update_ppe_status(
            actor=request.user, ppe_item=ppe_item, new_status=new_status
        )
        return Response({"availability_status": ppe_item.availability_status})
