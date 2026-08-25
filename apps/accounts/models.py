"""Custom user model with role-based access."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Application user.

    Two roles exist in Version 1: ADMIN (full management) and WORKER
    (self-scoped read access). Workers log in with credentials created by an
    admin when their profile is created.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        WORKER = "WORKER", "Worker"

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.WORKER,
        db_index=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["role", "is_active"]),
        ]

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def worker_profile(self):
        return getattr(self, "_worker_profile", None)
