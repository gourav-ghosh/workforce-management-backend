"""Worker management API (admin only)."""

from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import BusinessError, ResourceNotFound
from apps.common.pagination import DefaultPagination
from apps.common.permissions import IsAdminRole
from apps.workers import services
from apps.workers.filters import WorkerFilter
from apps.workers.models import WorkerProfile
from apps.workers.serializers import (
    AdminPasswordResetSerializer,
    WorkerDetailSerializer,
    WorkerListSerializer,
    WorkerSelfPasswordResetSerializer,
    WorkerWriteSerializer,
)

User = get_user_model()


class WorkerListCreateView(APIView):
    """GET /workers/ — list workers; POST /workers/ — create a worker."""

    permission_classes = [IsAdminRole]
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = WorkerFilter
    search_fields = ["full_name", "employee_id", "phone_number"]
    ordering_fields = ["full_name", "employee_id", "created_at"]

    def get(self, request):
        queryset = (
            WorkerProfile.objects.all().select_related("user").order_by("full_name", "employee_id")
        )
        for backend in self.filter_backends:
            queryset = backend().filter_queryset(self.request, queryset, self)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = WorkerListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = WorkerWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        worker = services.create_worker(
            actor=request.user, validated_data=dict(serializer.validated_data)
        )
        out = WorkerDetailSerializer(worker, context={"request": request}).data
        return Response(out, status=status.HTTP_201_CREATED)


class WorkerDetailView(APIView):
    """GET/PUT/PATCH/DELETE /workers/{id}/ — worker detail."""

    permission_classes = [IsAdminRole]

    def _get_worker(self, pk):
        try:
            return WorkerProfile.objects.select_related("user").get(pk=pk)
        except WorkerProfile.DoesNotExist:
            raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")

    def get(self, request, pk=None):
        worker = self._get_worker(pk)
        return Response(WorkerDetailSerializer(worker, context={"request": request}).data)

    def put(self, request, pk=None):
        worker = self._get_worker(pk)
        serializer = WorkerWriteSerializer(worker, data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_worker(
            actor=request.user,
            worker=worker,
            validated_data=dict(serializer.validated_data),
        )
        worker.refresh_from_db()
        return Response(WorkerDetailSerializer(worker, context={"request": request}).data)

    def patch(self, request, pk=None):
        worker = self._get_worker(pk)
        serializer = WorkerWriteSerializer(worker, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_worker(
            actor=request.user,
            worker=worker,
            validated_data=dict(serializer.validated_data),
        )
        worker.refresh_from_db()
        return Response(WorkerDetailSerializer(worker, context={"request": request}).data)

    def delete(self, request, pk=None):
        worker = self._get_worker(pk)
        services.delete_worker(actor=request.user, worker=worker)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkerResetPasswordView(APIView):
    """POST /workers/{id}/reset-password/ — admin sets a new password for a worker."""

    permission_classes = [IsAdminRole]

    def post(self, request, pk=None):
        try:
            worker = WorkerProfile.objects.select_related("user").get(pk=pk)
        except WorkerProfile.DoesNotExist:
            raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")

        serializer = AdminPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_worker_password(
            actor=request.user,
            worker=worker,
            new_password=serializer.validated_data["new_password"],
        )
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)


class WorkerSelfPasswordResetView(APIView):
    """POST /workers/self/reset-password/ — worker resets their own password
    using their current (default) password.
    """

    permission_classes = []

    def post(self, request):
        serializer = WorkerSelfPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mobile = serializer.validated_data["mobile_number"]
        new_password = serializer.validated_data["new_password"]

        user = User.objects.get(mobile_number=mobile)
        worker = user.worker_profile
        services.set_worker_password(
            actor=user,
            worker=worker,
            new_password=new_password,
        )
        return Response({"detail": "Password has been reset."}, status=status.HTTP_200_OK)
