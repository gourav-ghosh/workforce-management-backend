"""Vehicle and assignment models."""

from django.db import models

from apps.common.models import TimeStampedModel
from apps.common.validators import vehicle_media_upload_to, vehicle_photo_upload_to


class Vehicle(TimeStampedModel):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        IN_USE = "IN_USE", "In Use"
        UNDER_MAINTENANCE = "UNDER_MAINTENANCE", "Under Maintenance"
        RETIRED = "RETIRED", "Retired"

    class VehicleType(models.TextChoices):
        TRUCK = "TRUCK", "Truck"
        VAN = "VAN", "Van"
        PICKUP = "PICKUP", "Pickup"
        CAR = "CAR", "Car"
        BUS = "BUS", "Bus"
        TRAILER = "TRAILER", "Trailer"
        DUMPER = "DUMPER", "Dumper"
        OTHER = "OTHER", "Other"

    vehicle_id = models.CharField(max_length=50, unique=True)
    registration_number = models.CharField(max_length=20, unique=True, db_index=True)
    vehicle_type = models.CharField(max_length=10, choices=VehicleType.choices, db_index=True)
    make_model = models.CharField(max_length=150, blank=True)
    photo = models.ImageField(upload_to=vehicle_photo_upload_to, null=True, blank=True)
    driver = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicles_driven",
        help_text="Default driver for this vehicle.",
    )
    capacity = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
        db_index=True,
    )
    insurance_valid_until = models.DateField(null=True, blank=True)
    inspection_valid_until = models.DateField(null=True, blank=True)
    # Compliance / validity dates. All nullable — populated only when the
    # vehicle requires the corresponding certification.
    rc_validity = models.DateField(null=True, blank=True)
    fitness_validity = models.DateField(null=True, blank=True)
    pollution_validity = models.DateField(null=True, blank=True)
    safety_validity = models.DateField(null=True, blank=True)
    load_test_validity = models.DateField(null=True, blank=True)
    # Operational cost (currency is whatever the user enters; no auto FX).
    yearly_maintenance_charge = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Estimated annual maintenance cost (blank if unknown).",
    )
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["vehicle_id"]

    def __str__(self):
        return f"{self.vehicle_id} ({self.registration_number})"


class VehicleAssignment(TimeStampedModel):
    """Vehicle usage record.

    An assignment is open while ``end_datetime`` is NULL. Overlapping open or
    time-conflicting assignments are prevented by the assignment service.
    """

    class AssignmentType(models.TextChoices):
        PROJECT = "PROJECT", "Project"
        WORKER_TRANSPORT = "WORKER_TRANSPORT", "Worker Transport"
        MATERIAL_TRANSPORT = "MATERIAL_TRANSPORT", "Material Transport"
        GENERAL_USE = "GENERAL_USE", "General Company Use"
        OTHER = "OTHER", "Other"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="assignments")
    worker = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_assignments",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_assignments",
    )
    driver = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_assignments_driven",
    )
    assignment_type = models.CharField(max_length=20, choices=AssignmentType.choices, db_index=True)
    start_datetime = models.DateTimeField(db_index=True)
    end_datetime = models.DateTimeField(null=True, blank=True)
    purpose = models.CharField(max_length=255, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_datetime", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_datetime__isnull=True)
                | models.Q(end_datetime__gt=models.F("start_datetime")),
                name="chk_vehicle_assignment_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["vehicle", "end_datetime"]),
            models.Index(fields=["project", "start_datetime"]),
        ]

    def __str__(self):
        return f"{self.vehicle_id}:{self.assignment_type}:{self.start_datetime:%Y-%m-%d}"


class VehicleMedia(TimeStampedModel):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="media")
    file = models.ImageField(upload_to=vehicle_media_upload_to)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class VehicleBookingStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    CONFIRMED = "CONFIRMED", "Confirmed"
    CANCELLED = "CANCELLED", "Cancelled"
    COMPLETED = "COMPLETED", "Completed"


class VehicleBooking(TimeStampedModel):
    """A future reservation of a vehicle for a planned purpose.

    Distinct from [VehicleAssignment] (which is the actual usage record
    that opens a real `end_datetime = NULL` window). A booking does NOT
    mark the vehicle as `IN_USE`; it just blocks overlapping bookings
    for the same vehicle in the same window.
    """

    class BookingType(models.TextChoices):
        PROJECT = "PROJECT", "Project"
        WORKER_TRANSPORT = "WORKER_TRANSPORT", "Worker Transport"
        MATERIAL_TRANSPORT = "MATERIAL_TRANSPORT", "Material Transport"
        GENERAL_USE = "GENERAL_USE", "General Company Use"
        OTHER = "OTHER", "Other"

    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name="bookings"
    )
    booked_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_bookings",
    )
    driver = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_bookings_driven",
        help_text="Optional assigned driver for this booking.",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_bookings",
    )
    worker = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicle_bookings",
        help_text="Worker the booking is for (e.g. shift transport).",
    )
    booking_type = models.CharField(
        max_length=20, choices=BookingType.choices, db_index=True
    )
    start_datetime = models.DateTimeField(db_index=True)
    end_datetime = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=12,
        choices=VehicleBookingStatus.choices,
        default=VehicleBookingStatus.SCHEDULED,
        db_index=True,
    )
    purpose = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["start_datetime", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_datetime__gt=models.F("start_datetime")),
                name="chk_vehicle_booking_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["vehicle", "end_datetime"]),
            models.Index(fields=["status", "start_datetime"]),
        ]

    def __str__(self):
        return f"{self.vehicle_id}:{self.booking_type}:{self.start_datetime:%Y-%m-%d %H:%M}"
