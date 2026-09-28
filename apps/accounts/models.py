"""Custom user model with role-based access."""

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models


class MobileUserManager(DjangoUserManager):
    """Custom manager that uses ``mobile_number`` as the unique identifier."""

    use_in_migrations = True

    def _create_user(self, mobile_number, email, password, **extra_fields):
        if not mobile_number:
            raise ValueError("The mobile_number field must be set")
        email = self.normalize_email(email) if email else ""
        user = self.model(mobile_number=mobile_number, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, mobile_number, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(mobile_number, email, password, **extra_fields)

    def create_superuser(self, mobile_number, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "ADMIN")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(mobile_number, email, password, **extra_fields)


class User(AbstractUser):
    """Application user.

    Two roles exist in Version 1: ADMIN (full management) and WORKER
    (self-scoped read access). Workers log in with their mobile number and a
    password set by an admin when their profile is created. The legacy
    ``username`` field is retained for Django compatibility but is optional;
    mobile number is the primary login identifier.
    """

    username = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="Optional. Retained for Django compatibility; not used for login.",
    )

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        WORKER = "WORKER", "Worker"

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.WORKER,
        db_index=True,
    )

    mobile_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text="Used as the login identifier instead of username.",
    )

    USERNAME_FIELD = "mobile_number"
    REQUIRED_FIELDS = []

    objects = MobileUserManager()

    class Meta:
        indexes = [
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["mobile_number", "is_active"]),
        ]

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def worker_profile(self):
        return getattr(self, "_worker_profile", None)
