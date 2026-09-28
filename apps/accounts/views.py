"""Authentication and current-user endpoints."""

import logging

from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db.models import Count, Prefetch, Q
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.serializers import (
    ChangePasswordSerializer,
    MeSerializer,
    MyPPEAssignmentSerializer,
    MyProjectAssignmentSerializer,
    MyToolAssignmentSerializer,
    MyToolDamageReportInputSerializer,
    MyToolHistoryAssignmentSerializer,
    MyVehicleAssignmentSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)
from apps.common.exceptions import BusinessError, ResourceNotFound

logger = logging.getLogger(__name__)

User = get_user_model()


class LoginView(TokenObtainPairView):
    """POST /api/v1/auth/login/ — returns access/refresh tokens and user info."""

    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    """POST /api/v1/auth/refresh/"""


class LogoutView(APIView):
    """POST /api/v1/auth/logout/

    Blacklists the provided refresh token; when omitted, every outstanding
    refresh token of the user is blacklisted.
    """

    def post(self, request):
        refresh = request.data.get("refresh")
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                raise BusinessError(detail="Invalid refresh token.", code="INVALID_TOKEN")
            return Response(status=status.HTTP_204_NO_CONTENT)

        self._blacklist_all_user_tokens(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _blacklist_all_user_tokens(user):
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                BlacklistedToken,
                OutstandingToken,
            )

            for outstanding in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding)
        except ImportError:  # pragma: no cover - blacklist app is installed
            logger.warning("Token blacklist app unavailable; logout skipped blacklisting.")


class PasswordResetRequestView(APIView):
    """POST /api/v1/auth/password-reset/

    Always responds with 200 to avoid account enumeration. When SMTP is
    configured, an email containing reset credentials is sent.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"
    permission_classes = []

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"].strip()

        users = User.objects.filter(is_active=True).filter(
            Q(mobile_number__iexact=identifier) | Q(email__iexact=identifier)
        )
        for user in users:
            self._send_reset_email(user)

        return Response(
            {"detail": ("If the account exists, password reset instructions have been sent.")},
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _send_reset_email(user):
        if not user.email:
            logger.info("Password reset requested for user without email: id=%s", user.pk)
            return
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        try:
            send_mail(
                subject="Workforce Management - Password Reset",
                message=(
                    "Use the following values to reset your password.\n\n"
                    f"uid: {uid}\n"
                    f"token: {token}\n"
                ),
                from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            logger.exception("Failed sending password reset email for user id=%s", user.pk)


class PasswordResetConfirmView(APIView):
    """POST /api/v1/auth/password-reset/confirm/"""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"
    permission_classes = []

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uid = serializer.validated_data["uid"]
        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
        except (User.DoesNotExist, ValueError, TypeError):
            raise BusinessError(detail="Invalid reset link.", code="INVALID_RESET")

        if not default_token_generator.check_token(user, token):
            raise BusinessError(detail="Invalid or expired reset token.", code="INVALID_TOKEN")

        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response({"detail": "Password has been reset."}, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """POST /api/v1/auth/change-password/"""

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"detail": "Password changed."}, status=status.HTTP_200_OK)


class WorkerSelfPasswordResetView(APIView):
    """POST /api/v1/auth/password-reset/self/ — worker resets own password.

    A worker can reset their password using their current (default) password,
    or an admin can re-issue a default password and the worker can change it.
    """

    permission_classes = []

    def post(self, request):
        from apps.workers.models import WorkerProfile
        from apps.workers.serializers import WorkerSelfPasswordResetSerializer
        from apps.workers.services import set_worker_password

        serializer = WorkerSelfPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mobile = serializer.validated_data["mobile_number"]
        new_password = serializer.validated_data["new_password"]

        user = User.objects.get(mobile_number=mobile)
        worker = WorkerProfile.objects.get(user=user)
        set_worker_password(actor=user, worker=worker, new_password=new_password)
        return Response({"detail": "Password has been reset."}, status=status.HTTP_200_OK)


class MeView(APIView):
    """GET /api/v1/me/ — current user with nested worker profile."""

    def get(self, request):
        return Response(MeSerializer(request.user).data)


def _get_worker_profile(user):
    """Resolve the worker profile of the requesting user."""
    if user.role != User.Role.WORKER:
        raise BusinessError(
            detail="This endpoint is only available to worker accounts.",
            code="WORKER_ROLE_REQUIRED",
        )
    try:
        return user.worker_profile
    except Exception:
        raise BusinessError(
            detail="No worker profile is linked to this account.",
            code="WORKER_PROFILE_REQUIRED",
        )


class MeSummaryView(APIView):
    """GET /api/v1/me/summary/ — quick counts for the worker home screen."""

    def get(self, request):
        profile = _get_worker_profile(request.user)

        from apps.ppe.models import PPEAssignment
        from apps.projects.models import ProjectWorker
        from apps.tools.models import Tool, ToolAssignment
        from apps.transportation.services import open_vehicle_assignments_for_worker

        active_tools = ToolAssignment.objects.filter(
            worker=profile, status=ToolAssignment.Status.ACTIVE
        )
        active_tool_ids = list(active_tools.values_list("tool_id", flat=True))
        damaged_tool_count = Tool.objects.filter(
            pk__in=active_tool_ids,
            availability_status=Tool.AvailabilityStatus.DAMAGED,
        ).count()

        return Response(
            {
                "projects": ProjectWorker.objects.filter(worker=profile, is_active=True).count(),
                "tools": active_tools.count(),
                "tools_damaged": damaged_tool_count,
                "ppe": PPEAssignment.objects.filter(worker=profile, status="ACTIVE").count(),
                "vehicles": len(open_vehicle_assignments_for_worker(profile)),
            }
        )


class _MyListPaginatorMixin:
    """Shared helper for the ``/me/<x>`` list endpoints."""

    pagination_class = None  # set on each view; default behaviour is no pagination

    def _paginated(self, request, queryset, serializer_class, context=None):
        from apps.common.pagination import DefaultPagination

        paginator_class = self.pagination_class or DefaultPagination
        paginator = paginator_class()
        ctx = context or {"request": request}
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            data = serializer_class(page, many=True, context=ctx).data
            return paginator.get_paginated_response(data)
        data = serializer_class(queryset, many=True, context=ctx).data
        return Response(data)


class MyProjectsView(APIView, _MyListPaginatorMixin):
    """GET /api/v1/me/projects/ — projects currently assigned to the worker."""

    def get(self, request):
        profile = _get_worker_profile(request.user)
        from apps.projects.models import ProjectWorker

        qs = (
            ProjectWorker.objects.filter(worker=profile, is_active=True)
            .select_related("project")
            .order_by("-assigned_at")
        )
        return self._paginated(request, qs, MyProjectAssignmentSerializer)


class MyProjectDetailView(APIView):
    """GET /api/v1/me/projects/{id}/ — project detail for an assigned worker.

    Returns the same shape as the admin's ProjectDetailSerializer but
    restricted to projects where the worker is currently assigned. All write
    operations remain admin-only.
    """

    def get(self, request, pk=None):
        profile = _get_worker_profile(request.user)
        from apps.projects.models import Project, ProjectWorker
        from apps.projects.serializers import ProjectDetailSerializer

        try:
            assignment = ProjectWorker.objects.select_related("project").get(
                project_id=pk, worker=profile, is_active=True
            )
        except ProjectWorker.DoesNotExist:
            raise BusinessError(
                detail="You are not assigned to this project.",
                code="PROJECT_NOT_ASSIGNED",
            )

        project = Project.objects.annotate(
            active_workers_count=Count(
                "worker_assignments", filter=Q(worker_assignments__is_active=True)
            )
        ).get(pk=assignment.project_id)
        return Response(
            ProjectDetailSerializer(project, context={"request": request}).data
        )


class MyToolsView(APIView):
    """GET /api/v1/me/tools/ — tools currently issued to the worker."""

    def get(self, request):
        profile = _get_worker_profile(request.user)
        from apps.tools.models import ToolAssignment

        qs = (
            ToolAssignment.objects.filter(worker=profile, status="ACTIVE")
            .select_related("tool")
            .order_by("-issue_date", "-id")
        )
        return Response(
            MyToolAssignmentSerializer(qs, many=True, context={"request": request}).data
        )


class MyToolHistoryView(APIView, _MyListPaginatorMixin):
    """GET /api/v1/me/tools/history/ — full tool assignment history (active+past).

    Includes nested damage records with their photos and description so the
    worker can see everything that has been reported against the tools they
    were issued.
    """

    def get(self, request):
        from apps.tools.models import ToolAssignment, ToolMedia

        profile = _get_worker_profile(request.user)

        damage_prefetch = Prefetch(
            "damages__media",
            queryset=ToolMedia.objects.all(),
        )
        assignment_media_prefetch = Prefetch(
            "media",
            queryset=ToolMedia.objects.all(),
        )

        qs = (
            ToolAssignment.objects.filter(worker=profile)
            .select_related("tool")
            .prefetch_related(damage_prefetch, assignment_media_prefetch)
            .order_by("-issue_date", "-id")
        )
        return self._paginated(request, qs, MyToolHistoryAssignmentSerializer)


class MyPPEView(APIView):
    """GET /api/v1/me/ppe/ — PPE currently issued to the worker."""

    def get(self, request):
        profile = _get_worker_profile(request.user)
        from apps.ppe.models import PPEAssignment

        qs = (
            PPEAssignment.objects.filter(worker=profile, status="ACTIVE")
            .select_related("ppe")
            .order_by("-issue_date", "-id")
        )
        return Response(
            MyPPEAssignmentSerializer(qs, many=True, context={"request": request}).data
        )


class MyPerformanceView(APIView):
    """GET /api/v1/me/performance/ — worker's own performance evaluations.

    Only records with ``is_visible_to_worker=True`` are returned. In V1 the
    admin keeps this flag off by default; once flipped, the worker can see
    their own scores.
    """

    def get(self, request):
        from apps.performance.models import PerformanceRecord

        profile = _get_worker_profile(request.user)
        qs = (
            PerformanceRecord.objects.filter(worker=profile, is_visible_to_worker=True)
            .select_related("worker", "evaluator")
            .order_by("-period_end", "-id")
        )
        from apps.performance.serializers import PerformanceRecordSerializer

        return Response(PerformanceRecordSerializer(qs, many=True).data)


class MyVehiclesView(APIView):
    """GET /api/v1/me/vehicles/ — transportation where the worker is the
    assignee or the driver.
    """

    def get(self, request):
        profile = _get_worker_profile(request.user)
        from apps.transportation.services import open_vehicle_assignments_for_worker

        qs = open_vehicle_assignments_for_worker(profile)
        return Response(
            MyVehicleAssignmentSerializer(
                qs, many=True, context={"request": request, "worker_profile_id": profile.pk}
            ).data
        )


class MyToolDetailView(APIView):
    """GET /api/v1/me/tools/{assignment_id}/ — single tool assignment detail.

    Returns the same shape as the history serializer, scoped to a single
    assignment. Workers may only access their own assignments.
    """

    def get(self, request, assignment_id):
        from django.db.models import Prefetch

        from apps.tools.models import ToolAssignment, ToolMedia

        profile = _get_worker_profile(request.user)
        try:
            assignment = (
                ToolAssignment.objects.select_related("tool")
                .prefetch_related(
                    Prefetch("damages__media", queryset=ToolMedia.objects.all()),
                    Prefetch("media", queryset=ToolMedia.objects.all()),
                )
                .get(pk=assignment_id, worker=profile)
            )
        except ToolAssignment.DoesNotExist:
            raise ResourceNotFound(
                detail="Assignment not found.", code="ASSIGNMENT_NOT_FOUND"
            )
        return Response(
            MyToolHistoryAssignmentSerializer(assignment, context={"request": request}).data
        )


class MyToolDamageReportView(APIView):
    """POST /api/v1/me/tools/{assignment_id}/damage/ — worker reports damage
    against one of their own assignments.
    """

    parser_classes = ()  # JSON or multipart — let DRF default handle it via the parser set globally

    def get_parsers(self):
        from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

        return [MultiPartParser(), FormParser(), JSONParser()]

    def post(self, request, assignment_id):
        from apps.tools.services import record_tool_damage

        serializer = MyToolDamageReportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        photos = data.pop("photos", [])

        profile = _get_worker_profile(request.user)
        damage = record_tool_damage(
            actor=request.user,
            tool_id=None,  # resolved via assignment
            damage_description=data["damage_description"],
            damage_condition=data["damage_condition"],
            damage_date=None,
            repair_status=None,
            assignment_id=assignment_id,
            worker_profile=profile,
            remarks=data.get("remarks", ""),
            media_files=photos,
        )

        from apps.tools.serializers import ToolDamageReadSerializer

        return Response(
            ToolDamageReadSerializer(damage, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
