"""PPE catalogue and assignment models."""

from django.db import models

from apps.common.models import TimeStampedModel
from apps.common.validators import ppe_media_upload_to, ppe_photo_upload_to


class PPE(TimeStampedModel):
    class PPEType(models.TextChoices):
        HELMET = "HELMET", "Safety Helmet"
        SHOES = "SHOES", "Safety Shoes"
        GLOVES = "GLOVES", "Gloves"
        JACKET = "JACKET", "Safety Jacket"
        HARNESS = "HARNESS", "Safety Harness"
        GOGGLES = "GOGGLES", "Safety Goggles"
        EAR_PROTECTION = "EAR_PROTECTION", "Ear Protection"
        OTHER = "OTHER", "Other"

    class AvailabilityStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        ASSIGNED = "ASSIGNED", "Assigned"
        DAMAGED = "DAMAGED", "Damaged"
        EXPIRED = "EXPIRED", "Expired"
        RETIRED = "RETIRED", "Retired"

    class Condition(models.TextChoices):
        EXCELLENT = "EXCELLENT", "Excellent"
        GOOD = "GOOD", "Good"
        FAIR = "FAIR", "Fair"
        POOR = "POOR", "Poor"
        DAMAGED = "DAMAGED", "Damaged"

    ppe_id = models.CharField(max_length=50, unique=True)
    ppe_type = models.CharField(max_length=15, choices=PPEType.choices, db_index=True)
    name = models.CharField(max_length=200, db_index=True)
    category = models.CharField(max_length=100, blank=True)
    size = models.CharField(max_length=20, blank=True)
    total_quantity = models.IntegerField(default=0)
    available_quantity = models.IntegerField(default=0)
    photo = models.ImageField(upload_to=ppe_photo_upload_to, null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    condition = models.CharField(
        max_length=10,
        choices=Condition.choices,
        default=Condition.GOOD,
    )
    availability_status = models.CharField(
        max_length=10,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.AVAILABLE,
        db_index=True,
    )
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["ppe_id"]

    def __str__(self):
        return f"{self.ppe_id} - {self.name}"


class PPEAssignment(TimeStampedModel):
    """Immutable issue/return record for a PPE item."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        RETURNED = "RETURNED", "Returned"
        CANCELLED = "CANCELLED", "Cancelled"

    ppe = models.ForeignKey(PPE, on_delete=models.CASCADE, related_name="assignments")
    worker = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.PROTECT,
        related_name="ppe_assignments",
    )
    issue_date = models.DateField(db_index=True)
    expected_return_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    issue_condition = models.CharField(max_length=10, choices=PPE.Condition.choices)
    return_condition = models.CharField(
        max_length=10, choices=PPE.Condition.choices, null=True, blank=True
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-issue_date", "-id"]
        indexes = [
            models.Index(fields=["worker", "status"]),
        ]

    def __str__(self):
        return f"{self.ppe_id}:{self.worker_id}:{self.status}"


class PPEMedia(TimeStampedModel):
    class MediaType(models.TextChoices):
        GENERAL = "GENERAL", "General"
        ISSUE = "ISSUE", "Issue"
        RETURN = "RETURN", "Return"
        DAMAGE = "DAMAGE", "Damage"

    ppe = models.ForeignKey(PPE, on_delete=models.CASCADE, related_name="media")
    assignment = models.ForeignKey(
        PPEAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media",
    )
    media_type = models.CharField(
        max_length=10, choices=MediaType.choices, default=MediaType.GENERAL
    )
    file = models.ImageField(upload_to=ppe_media_upload_to)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["ppe", "media_type"]),
        ]
