"""Worker profile model."""

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.common.validators import worker_photo_upload_to


class WorkerProfile(TimeStampedModel):
    """HR information about a worker.

    Every worker has a linked login ``User`` created together with the
    profile; the account is deactivated when employment status becomes
    INACTIVE.
    """

    class EmploymentStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="worker_profile",
    )
    employee_id = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=150, db_index=True)
    phone_number = models.CharField(max_length=20, db_index=True)
    designation = models.CharField(max_length=100, blank=True)
    employment_status = models.CharField(
        max_length=10,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
        db_index=True,
    )
    # Supervisors keep the WORKER role (so they retain all /me/* self-service)
    # but gain the ability to mark attendance for workers on the projects
    # they are assigned to. Admins can mark attendance for anyone.
    is_supervisor = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Allows this worker to mark attendance for their project team.",
    )
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    profile_photo = models.ImageField(
        upload_to=worker_photo_upload_to,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["employment_status", "full_name"]),
        ]

    def __str__(self):
        return f"{self.employee_id} - {self.full_name}"
