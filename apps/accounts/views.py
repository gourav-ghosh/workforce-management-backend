"""Authentication and current-user endpoints."""

import logging

from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db.models import Q
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.generics import ListAPIView
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
    MyVehicleAssignmentSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)
from apps.common.exceptions import BusinessError

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
            Q(username__iexact=identifier) | Q(email__iexact=identifier)
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
            # Workers may not have an email on file; admins reset those
            # passwords directly (see workers reset-password endpoint).
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
        from apps.tools.models import ToolAssignment
        from apps.transportation.services import open_vehicle_assignments_for_worker

        return Response(
            {
                "projects": ProjectWorker.objects.filter(worker=profile, is_active=True).count(),
                "tools": ToolAssignment.objects.filter(worker=profile, status="ACTIVE").count(),
                "ppe": PPEAssignment.objects.filter(worker=profile, status="ACTIVE").count(),
                "vehicles": len(open_vehicle_assignments_for_worker(profile)),
            }
        )


class MyProjectsView(ListAPIView):
    """GET /api/v1/me/projects/ — projects currently assigned to the worker."""

    serializer_class = MyProjectAssignmentSerializer

    def get_queryset(self):
        profile = _get_worker_profile(self.request.user)
        from apps.projects.models import ProjectWorker

        return (
            ProjectWorker.objects.filter(worker=profile, is_active=True)
            .select_related("project")
            .order_by("-assigned_at")
        )


class MyToolsView(ListAPIView):
    """GET /api/v1/me/tools/ — tools currently issued to the worker."""

    serializer_class = MyToolAssignmentSerializer

    def get_queryset(self):
        profile = _get_worker_profile(self.request.user)
        from apps.tools.models import ToolAssignment

        return (
            ToolAssignment.objects.filter(worker=profile, status="ACTIVE")
            .select_related("tool")
            .order_by("-issue_date", "-id")
        )


class MyPPEView(ListAPIView):
    """GET /api/v1/me/ppe/ — PPE currently issued to the worker."""

    serializer_class = MyPPEAssignmentSerializer

    def get_queryset(self):
        profile = _get_worker_profile(self.request.user)
        from apps.ppe.models import PPEAssignment

        return (
            PPEAssignment.objects.filter(worker=profile, status="ACTIVE")
            .select_related("ppe")
            .order_by("-issue_date", "-id")
        )


class MyVehiclesView(ListAPIView):
    """GET /api/v1/me/vehicles/ — transportation where the worker is the
    assignee or the driver."""

    serializer_class = MyVehicleAssignmentSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        try:
            context["worker_profile_id"] = self.request.user.worker_profile.pk
        except Exception:
            context["worker_profile_id"] = None
        return context

    def get_queryset(self):
        profile = _get_worker_profile(self.request.user)
        from apps.transportation.services import open_vehicle_assignments_for_worker

        return open_vehicle_assignments_for_worker(profile)
