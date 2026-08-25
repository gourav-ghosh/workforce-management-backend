"""Project/order models."""

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.common.validators import generate_document_upload_path


class Project(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PLANNED = "PLANNED", "Planned"
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class MeasurementSheetStatus(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        NOT_SUBMITTED = "NOT_SUBMITTED", "Not submitted"

    project_number = models.CharField(max_length=50, unique=True)
    project_name = models.CharField(max_length=200, db_index=True)
    client_name = models.CharField(max_length=200, blank=True, db_index=True)
    location = models.CharField(max_length=255, blank=True, db_index=True)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    expected_completion_date = models.DateField(null=True, blank=True)
    permit_no = models.CharField(max_length=50, blank=True)
    total_manpower = models.PositiveIntegerField(null=True, blank=True)
    job = models.CharField(max_length=200, blank=True)
    measurement_sheet_status = models.CharField(
        max_length=15,
        choices=MeasurementSheetStatus.choices,
        default=MeasurementSheetStatus.NOT_SUBMITTED,
        db_index=True,
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    project_plan = models.FileField(
        upload_to=generate_document_upload_path,
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "start_date"]),
        ]

    def __str__(self):
        return f"{self.project_number} - {self.project_name}"


class ProjectWorker(TimeStampedModel):
    """Explicit worker assignment with history.

    Re-assigning a worker after unassignment creates a new row so the
    assignment history is never overwritten.
    """

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="worker_assignments"
    )
    worker = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.CASCADE,
        related_name="project_assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    unassigned_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "worker"],
                condition=models.Q(is_active=True),
                name="uniq_active_project_worker",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "is_active"]),
        ]

    def __str__(self):
        return f"{self.project_id}:{self.worker_id} active={self.is_active}"
