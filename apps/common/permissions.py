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
