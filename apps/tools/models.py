"""Tool catalogue and assignment models."""

from django.db import models

from apps.common.models import TimeStampedModel
from apps.common.validators import tool_media_upload_to, tool_photo_upload_to


class Tool(TimeStampedModel):
    class AvailabilityStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        ASSIGNED = "ASSIGNED", "Assigned"
        DAMAGED = "DAMAGED", "Damaged"
        UNDER_MAINTENANCE = "UNDER_MAINTENANCE", "Under Maintenance"
        LOST = "LOST", "Lost"
        RETIRED = "RETIRED", "Retired"

    class Condition(models.TextChoices):
        EXCELLENT = "EXCELLENT", "Excellent"
        GOOD = "GOOD", "Good"
        FAIR = "FAIR", "Fair"
        POOR = "POOR", "Poor"
        DAMAGED = "DAMAGED", "Damaged"

    tool_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200, db_index=True)
    category = models.CharField(max_length=100, blank=True, db_index=True)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to=tool_photo_upload_to, null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    condition = models.CharField(
        max_length=10,
        choices=Condition.choices,
        default=Condition.GOOD,
    )
    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.AVAILABLE,
        db_index=True,
    )
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["tool_id"]

    def __str__(self):
        return f"{self.tool_id} - {self.name}"


class ToolAssignment(TimeStampedModel):
    """Immutable issue/return record. History is never overwritten."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        RETURNED = "RETURNED", "Returned"
        CANCELLED = "CANCELLED", "Cancelled"

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="assignments")
    worker = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.PROTECT,
        related_name="tool_assignments",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tool_assignments",
    )
    issue_date = models.DateField(db_index=True)
    expected_return_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    issue_condition = models.CharField(max_length=10, choices=Tool.Condition.choices)
    return_condition = models.CharField(
        max_length=10, choices=Tool.Condition.choices, null=True, blank=True
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-issue_date", "-id"]
        constraints = [
            # A tool cannot have two simultaneous active assignments.
            models.UniqueConstraint(
                fields=["tool"],
                condition=models.Q(status="ACTIVE"),
                name="uniq_tool_active_assignment",
            ),
        ]
        indexes = [
            models.Index(fields=["worker", "status"]),
            models.Index(fields=["project", "status"]),
        ]

    def __str__(self):
        return f"{self.tool_id}:{self.worker_id}:{self.status}"


class ToolDamage(TimeStampedModel):
    class RepairStatus(models.TextChoices):
        REPORTED = "REPORTED", "Reported"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="damages")
    assignment = models.ForeignKey(
        ToolAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="damages",
    )
    damage_date = models.DateField(db_index=True)
    damage_description = models.TextField()
    damage_condition = models.CharField(max_length=10, choices=Tool.Condition.choices)
    repair_status = models.CharField(
        max_length=12,
        choices=RepairStatus.choices,
        default=RepairStatus.REPORTED,
        db_index=True,
    )
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-damage_date", "-id"]

    def __str__(self):
        return f"Damage {self.tool_id} {self.damage_date}"


class ToolMedia(TimeStampedModel):
    class MediaType(models.TextChoices):
        GENERAL = "GENERAL", "General"
        ISSUE = "ISSUE", "Issue"
        RETURN = "RETURN", "Return"
        DAMAGE = "DAMAGE", "Damage"

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="media")
    assignment = models.ForeignKey(
        ToolAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media",
    )
    damage = models.ForeignKey(
        ToolDamage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media",
    )
    media_type = models.CharField(
        max_length=10, choices=MediaType.choices, default=MediaType.GENERAL
    )
    file = models.ImageField(upload_to=tool_media_upload_to)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tool", "media_type"]),
        ]
