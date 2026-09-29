"""Shared permission classes.

Authorization is enforced here on the backend; the mobile client only hides
UI that a role cannot use anyway.
"""

from rest_framework.permissions import BasePermission

from apps.accounts.models import User


class IsAdminRole(BasePermission):
    """Allows access only to users with the ADMIN role."""

    message = "Only administrators can perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.ADMIN)


def supervisor_profile(user):
    """Return the WorkerProfile of a supervisor, or None.

    A supervisor keeps the WORKER role and is flagged with
    ``WorkerProfile.is_supervisor``. Accessing the reverse one-to-one raises
    when no profile is linked, so it is guarded here.
    """
    from apps.workers.models import WorkerProfile

    if not (user and user.is_authenticated) or user.role != User.Role.WORKER:
        return None
    try:
        profile = user.worker_profile
    except WorkerProfile.DoesNotExist:
        return None
    return profile if profile and profile.is_supervisor else None


class IsAdminOrSupervisor(BasePermission):
    """Allows admins, and workers explicitly flagged as supervisors."""

    message = "Only administrators and supervisors can perform this action."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.role == User.Role.ADMIN:
            return True
        return supervisor_profile(user) is not None
