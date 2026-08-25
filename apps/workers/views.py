"""Worker management API (admin only)."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminRole
from apps.workers import services
from apps.workers.filters import WorkerFilter
from apps.workers.models import WorkerProfile
from apps.workers.serializers import (
    AdminPasswordResetSerializer,
    WorkerDetailSerializer,
    WorkerListSerializer,
    WorkerWriteSerializer,
)


class WorkerViewSet(ModelViewSet):
    """CRUD for worker profiles."""

    permission_classes = [IsAdminRole]
    queryset = (
        WorkerProfile.objects.all().select_related("user").order_by("full_name", "employee_id")
    )
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = WorkerFilter
    search_fields = ["full_name", "employee_id", "phone_number"]
    ordering_fields = ["full_name", "employee_id", "created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return WorkerListSerializer
        if self.action == "retrieve":
            return WorkerDetailSerializer
        return WorkerWriteSerializer

    def perform_create(self, serializer):
        serializer.instance = services.create_worker(
            actor=self.request.user, validated_data=dict(serializer.validated_data)
        )

    def perform_update(self, serializer):
        serializer.instance = services.update_worker(
            actor=self.request.user,
            worker=serializer.instance,
            validated_data=dict(serializer.validated_data),
        )

    def perform_destroy(self, instance):
        services.delete_worker(actor=self.request.user, worker=instance)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        worker = self.get_object()
        serializer = AdminPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_worker_password(
            actor=request.user,
            worker=worker,
            new_password=serializer.validated_data["new_password"],
        )
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)
