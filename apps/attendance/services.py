"""Attendance workflows: scope checks plus create/update/delete services."""

from datetime import timedelta

from django.db import transaction

from apps.attendance.models import (
    AttendanceRecord,
    max_backdate_days,
    today_in_attendance_tz,
)
from apps.audit.services import record_audit
from apps.common.exceptions import BusinessError, ResourceNotFound
from apps.projects.models import Project, ProjectWorker
from apps.workers.models import WorkerProfile


def is_admin(user):
    return bool(user and user.is_authenticated and user.role == "ADMIN")


def supervised_project_ids(supervisor):
    """Project IDs the supervisor is currently assigned to."""
    if not supervisor:
        return set()
    return set(
        ProjectWorker.objects.filter(worker=supervisor, is_active=True).values_list(
            "project_id", flat=True
        )
    )


def assert_can_mark_for(user, supervisor, project_id):
    """Admins may mark anyone; supervisors only within their own projects."""
    if is_admin(user):
        return
    allowed = supervised_project_ids(supervisor)
    if project_id not in allowed:
        raise BusinessError(
            detail=("You can only mark attendance for workers on projects you are assigned to."),
            code="SUPERVISOR_OUT_OF_SCOPE",
        )


def assert_worker_assigned_to_project(worker, project):
    """Supervisor writes must belong to a worker on the project.

    Historical (unassigned) rows still count, so closing out a past day after
    someone was unassigned does not become impossible. Admins skip this check
    entirely - they may log attendance for anyone, with or without a project.
    """
    if not ProjectWorker.objects.filter(project=project, worker=worker).exists():
        raise BusinessError(
            detail=f"{worker.full_name} is not assigned to {project.project_number}.",
            code="WORKER_NOT_ON_PROJECT",
        )


def assert_date_allowed(value):
    """Attendance is a daily log: today or up to N days back, never ahead."""
    today = today_in_attendance_tz()
    if value > today:
        raise BusinessError(
            detail="Attendance cannot be recorded for a future date.",
            code="ATTENDANCE_FUTURE_DATE",
        )
    if value < today - timedelta(days=max_backdate_days()):
        raise BusinessError(
            detail=(
                f"Attendance can only be recorded for today or the previous "
                f"{max_backdate_days()} days."
            ),
            code="ATTENDANCE_TOO_OLD",
        )


def get_visible_records(user, supervisor):
    """Queryset of attendance records the user is allowed to see.

    A supervisor only sees records tied to one of their projects, so the
    admin's project-less company-wide entries stay out of their list.
    """
    qs = AttendanceRecord.objects.select_related("worker", "project", "recorded_by")
    if is_admin(user):
        return qs
    return qs.filter(project_id__in=supervised_project_ids(supervisor))


def _assert_unique(worker, project, date, exclude_pk=None):
    """One record per worker per day (per project when a project is given)."""
    clash = AttendanceRecord.objects.filter(worker=worker, date=date)
    if project is not None:
        clash = clash.filter(project=project)
    else:
        clash = clash.filter(project__isnull=True)
    if exclude_pk is not None:
        clash = clash.exclude(pk=exclude_pk)
    if clash.exists():
        target = project.project_number if project is not None else "no project"
        raise BusinessError(
            detail=(f"Attendance for {worker.full_name} on {date} ({target}) is already recorded."),
            code="ATTENDANCE_ALREADY_RECORDED",
        )


def _resolve_project(project_id, actor, supervisor):
    """Return the Project, or None for an admin company-wide entry."""
    if project_id in (None, ""):
        if is_admin(actor):
            return None
        raise BusinessError(
            detail="Supervisors must choose one of their projects.",
            code="PROJECT_REQUIRED",
        )
    try:
        return Project.objects.get(pk=project_id)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise ResourceNotFound(detail="Project does not exist.", code="PROJECT_NOT_FOUND")


@transaction.atomic
def mark_attendance(*, actor, supervisor, worker_id, project_id, validated_data):
    """Create one attendance record after validating scope and assignment."""
    try:
        worker = WorkerProfile.objects.get(pk=worker_id)
    except (WorkerProfile.DoesNotExist, ValueError, TypeError):
        raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")

    project = _resolve_project(project_id, actor, supervisor)

    # An admin may log attendance for anyone, with or without a project.
    # A supervisor is confined to their own projects and their team.
    if project is not None:
        assert_can_mark_for(actor, supervisor, project.pk)
        if not is_admin(actor):
            assert_worker_assigned_to_project(worker, project)

    date = validated_data["date"]
    assert_date_allowed(date)
    _assert_unique(worker, project, date)

    # The write serializer hands back WorkerProfile/Project instances for
    # worker/project, so drop them before create() to avoid duplicate kwargs.
    fields = {
        key: value for key, value in validated_data.items() if key not in ("worker", "project")
    }
    record = AttendanceRecord.objects.create(
        worker=worker,
        project=project,
        recorded_by=actor if getattr(actor, "is_authenticated", False) else None,
        **fields,
    )
    record_audit(
        action="ATTENDANCE_MARKED",
        entity=record,
        actor=actor,
        metadata={
            "worker_id": worker.pk,
            "project_id": project.pk if project else None,
            "date": str(date),
            "punch_in": record.punch_in.isoformat(),
            "punch_out": record.punch_out.isoformat() if record.punch_out else None,
            "is_late": record.is_late,
            "work_hours": record.work_hours,
        },
    )
    return record


@transaction.atomic
def update_attendance(*, actor, supervisor, record, validated_data):
    """Update a record. Scope is re-checked against the *new* project too."""
    # An explicit `project: null` clears the project, so the key's presence -
    # not its value - decides whether the project is being changed.
    if "project" in validated_data:
        project = validated_data["project"]
        if project is None and not is_admin(actor):
            raise BusinessError(
                detail="Only an admin can make a record project-less.",
                code="PROJECT_REQUIRED",
            )
    else:
        project = record.project
    worker_ref = validated_data.get("worker")
    worker_id = worker_ref.pk if worker_ref is not None else record.worker_id
    try:
        worker = WorkerProfile.objects.get(pk=worker_id)
    except (WorkerProfile.DoesNotExist, ValueError, TypeError):
        raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")

    if project is not None:
        assert_can_mark_for(actor, supervisor, project.pk)
        if not is_admin(actor):
            assert_worker_assigned_to_project(worker, project)

    date = validated_data.get("date", record.date)
    assert_date_allowed(date)
    _assert_unique(worker, project, date, exclude_pk=record.pk)

    for field, value in validated_data.items():
        setattr(record, field, value)
    record.save()

    record_audit(
        action="ATTENDANCE_UPDATED",
        entity=record,
        actor=actor,
        metadata={
            "worker_id": record.worker_id,
            "project_id": record.project_id,
            "date": str(record.date),
        },
    )
    return record


@transaction.atomic
def delete_attendance(*, actor, record):
    """Delete a record. Admin-only; the view enforces that."""
    record_audit(
        action="ATTENDANCE_DELETED",
        entity=record,
        actor=actor,
        metadata={
            "worker_id": record.worker_id,
            "project_id": record.project_id,
            "date": str(record.date),
        },
    )
    record.delete()
