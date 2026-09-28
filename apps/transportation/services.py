"""Vehicle workflows: assign/unassign with overlap prevention."""

import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import record_audit
from apps.common.exceptions import BusinessError, ResourceNotFound
from apps.transportation.models import (
    Vehicle,
    VehicleAssignment,
    VehicleBooking,
    VehicleBookingStatus,
)

logger = logging.getLogger(__name__)


def _assert_deletable(vehicle):
    if vehicle.assignments.exists():
        raise BusinessError(
            detail="Vehicle has assignment history and cannot be deleted.",
            code="RESOURCE_HAS_HISTORY",
        )


def _get_vehicle_for_update(vehicle_id):
    lookup = (
        {"pk": int(vehicle_id)}
        if isinstance(vehicle_id, int) or (isinstance(vehicle_id, str) and vehicle_id.isdigit())
        else {"vehicle_id": vehicle_id}
    )
    try:
        return Vehicle.objects.select_for_update().get(**lookup)
    except Vehicle.DoesNotExist:
        raise ResourceNotFound(detail="Vehicle does not exist.", code="VEHICLE_NOT_FOUND")


@transaction.atomic
def assign_vehicle(
    *,
    actor,
    vehicle_id,
    assignment_type,
    start_datetime,
    end_datetime=None,
    project_id=None,
    worker_id=None,
    driver_id=None,
    purpose="",
    remarks="",
):
    vehicle = _get_vehicle_for_update(vehicle_id)

    if vehicle.status in (Vehicle.Status.RETIRED, Vehicle.Status.UNDER_MAINTENANCE):
        raise BusinessError(
            detail=f"Vehicle is not assignable (status: {vehicle.status}).",
            code="VEHICLE_NOT_AVAILABLE",
        )

    if end_datetime is not None and end_datetime <= start_datetime:
        raise BusinessError(
            detail="End date/time must be after the start date/time.",
            code="INVALID_DATE_RANGE",
        )

    from apps.projects.models import Project

    project = None
    if project_id is not None:
        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            raise ResourceNotFound(detail="Project does not exist.", code="PROJECT_NOT_FOUND")

    from apps.workers.models import WorkerProfile

    worker = driver = None
    if worker_id is not None:
        worker = WorkerProfile.objects.filter(pk=worker_id).first()
        if not worker:
            raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")
    if driver_id is not None:
        driver = WorkerProfile.objects.filter(pk=driver_id).first()
        if not driver:
            raise ResourceNotFound(detail="Driver does not exist.", code="WORKER_NOT_FOUND")

    # Context rule: at least one of project/worker/purpose must be present.
    if project is None and worker is None and not (purpose or "").strip():
        raise BusinessError(
            detail=("Provide a project, a worker, or a purpose to describe the vehicle usage."),
            code="MISSING_ASSIGNMENT_CONTEXT",
        )

    _assert_no_overlap(vehicle, start_datetime, end_datetime)

    assignment = VehicleAssignment.objects.create(
        vehicle=vehicle,
        worker=worker,
        project=project,
        driver=driver,
        assignment_type=assignment_type,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        purpose=purpose or "",
        remarks=remarks or "",
    )

    # V1 assumption: an assignment marks the vehicle as in use immediately.
    if vehicle.status == Vehicle.Status.AVAILABLE:
        vehicle.status = Vehicle.Status.IN_USE
        vehicle.save(update_fields=["status", "updated_at"])

    record_audit(
        action="VEHICLE_ASSIGNED",
        entity=assignment,
        actor=actor,
        metadata={
            "vehicle_id": vehicle.pk,
            "registration_number": vehicle.registration_number,
            "assignment_type": assignment_type,
            "project_id": project.pk if project else None,
            "worker_id": worker.pk if worker else None,
            "start": str(start_datetime),
            "end": str(end_datetime) if end_datetime else None,
        },
    )
    logger.info("Vehicle %s assigned (%s)", vehicle.vehicle_id, assignment_type)
    return assignment


def _assert_no_overlap(vehicle, start_datetime, end_datetime):
    """Reject conflicting overlapping assignments.

    An existing open-ended assignment blocks everything starting at/after its
    start; bounded assignments conflict when their ranges intersect.
    """
    qs = vehicle.assignments.filter(end_datetime__isnull=True).filter(
        start_datetime__lte=end_datetime if end_datetime else start_datetime
    )
    if end_datetime is None:
        conflict_open = (
            qs.exists() or vehicle.assignments.filter(end_datetime__gte=start_datetime).exists()
        )
        conflict_bounded = False
    else:
        conflict_open = qs.filter(start_datetime__lte=end_datetime).exists()
        conflict_bounded = vehicle.assignments.filter(
            end_datetime__isnull=False,
            start_datetime__lt=end_datetime,
            end_datetime__gt=start_datetime,
        ).exists()
    if conflict_open or conflict_bounded:
        raise BusinessError(
            detail="The vehicle already has an assignment overlapping this period.",
            code="VEHICLE_OVERLAP",
        )


@transaction.atomic
def unassign_vehicle(*, actor, vehicle_id, assignment_id=None, end_datetime=None):
    """Close the current (or given) open assignment."""
    vehicle = _get_vehicle_for_update(vehicle_id)

    qs = vehicle.assignments.select_for_update().filter(end_datetime__isnull=True)
    if assignment_id is not None:
        qs = qs.filter(pk=assignment_id)
    assignment = qs.order_by("-start_datetime").first()
    if not assignment:
        raise BusinessError(
            detail="Vehicle has no open assignment to close.",
            code="NO_ACTIVE_ASSIGNMENT",
        )

    effective_end = end_datetime or timezone.now()
    if effective_end <= assignment.start_datetime:
        raise BusinessError(
            detail="End date/time must be after the assignment start.",
            code="INVALID_DATE_RANGE",
        )
    assignment.end_datetime = effective_end
    assignment.save(update_fields=["end_datetime", "updated_at"])

    still_in_use = (
        vehicle.assignments.filter(end_datetime__isnull=True)
        .filter(start_datetime__lte=timezone.now())
        .exists()
    )
    if not still_in_use and vehicle.status == Vehicle.Status.IN_USE:
        vehicle.status = Vehicle.Status.AVAILABLE
        vehicle.save(update_fields=["status", "updated_at"])

    record_audit(
        action="VEHICLE_UNASSIGNED",
        entity=assignment,
        actor=actor,
        metadata={"vehicle_id": vehicle.pk, "ended_at": str(effective_end)},
    )
    return assignment


@transaction.atomic
def update_vehicle_status(*, actor, vehicle, new_status):
    current = vehicle.status
    vehicle.status = new_status
    vehicle.save(update_fields=["status", "updated_at"])
    record_audit(
        action="VEHICLE_STATUS_CHANGED",
        entity=vehicle,
        actor=actor,
        metadata={"from": current, "to": new_status},
    )
    return vehicle


@transaction.atomic
def delete_vehicle(*, actor, vehicle):
    _assert_deletable(vehicle)
    record_audit(
        action="VEHICLE_DELETED",
        entity_type="Vehicle",
        entity_id=str(vehicle.pk),
        actor=actor,
        metadata={"registration_number": vehicle.registration_number},
    )
    vehicle.delete()


def open_vehicle_assignments_for_worker(worker_profile):
    now = timezone.now()
    return (
        VehicleAssignment.objects.select_related("vehicle", "project")
        .filter(
            Q(end_datetime__isnull=True),
            start_datetime__lte=now,
        )
        .filter(Q(worker=worker_profile) | Q(driver=worker_profile))
        .order_by("-start_datetime")
    )


def _assert_no_booking_overlap(vehicle, start_datetime, end_datetime, exclude_id=None):
    qs = vehicle.bookings.exclude(
        status=VehicleBookingStatus.CANCELLED
    )
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    for b in qs:
        if b.start_datetime < end_datetime and start_datetime < b.end_datetime:
            raise BusinessError(
                detail=(
                    f"Vehicle {vehicle.vehicle_id} already has a booking from "
                    f"{b.start_datetime:%Y-%m-%d %H:%M} to {b.end_datetime:%Y-%m-%d %H:%M}."
                ),
                code="BOOKING_OVERLAP",
            )


@transaction.atomic
def create_vehicle_booking(*, actor, vehicle, validated_data):
    start = validated_data["start_datetime"]
    end = validated_data["end_datetime"]
    if end <= start:
        raise BusinessError(
            detail="end_datetime must be after start_datetime.",
            code="INVALID_DATE_RANGE",
        )
    if start <= timezone.now():
        raise BusinessError(
            detail="start_datetime must be in the future.",
            code="BOOKING_MUST_BE_FUTURE",
        )
    _assert_no_booking_overlap(vehicle, start, end)
    booking = VehicleBooking.objects.create(
        vehicle=vehicle,
        booked_by=actor,
        **validated_data,
    )
    record_audit(
        action="VEHICLE_BOOKED",
        entity=booking,
        actor=actor,
        metadata={
            "vehicle_id": vehicle.pk,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "type": booking.booking_type,
        },
    )
    return booking


@transaction.atomic
def update_vehicle_booking(*, booking, validated_data):
    new_start = validated_data.get("start_datetime", booking.start_datetime)
    new_end = validated_data.get("end_datetime", booking.end_datetime)
    if new_end <= new_start:
        raise BusinessError(
            detail="end_datetime must be after start_datetime.",
            code="INVALID_DATE_RANGE",
        )
    if "start_datetime" in validated_data and new_start <= timezone.now():
        raise BusinessError(
            detail="start_datetime must be in the future.",
            code="BOOKING_MUST_BE_FUTURE",
        )
    _assert_no_booking_overlap(
        booking.vehicle, new_start, new_end, exclude_id=booking.pk
    )
    for field, value in validated_data.items():
        setattr(booking, field, value)
    booking.save()
    record_audit(
        action="VEHICLE_BOOKING_UPDATED",
        entity=booking,
        actor=booking.booked_by,
        metadata={"booking_id": booking.pk},
    )
    return booking


@transaction.atomic
def delete_vehicle_booking(*, actor, booking):
    record_audit(
        action="VEHICLE_BOOKING_CANCELLED",
        entity=booking,
        actor=actor,
        metadata={"booking_id": booking.pk},
    )
    booking.delete()
