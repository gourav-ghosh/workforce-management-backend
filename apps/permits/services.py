"""TBM & work-permit workflows: scope checks plus create/update/delete.

The scope rules intentionally mirror attendance: a supervisor is confined to
the projects they are assigned to and the workers on those projects, while an
admin is unrestricted. Reusing the vocabulary means the clients only have to
learn one set of error codes.
"""

from django.db import transaction

from apps.common.exceptions import BusinessError, ResourceNotFound
from apps.permits.models import (
    WorkPermit,
    earliest_allowed_date,
    today_in_permits_tz,
)
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


def assert_can_manage(user, supervisor, project_id):
    """Admins may act on any project; supervisors only within their own."""
    if is_admin(user):
        return
    if project_id not in supervised_project_ids(supervisor):
        raise BusinessError(
            detail="You can only manage permits for projects you are assigned to.",
            code="SUPERVISOR_OUT_OF_SCOPE",
        )


def assert_workers_assigned_to_project(workers, project):
    """A supervisor's permit must only name workers on the project.

    Admins are deliberately not checked: they may record a permit for any
    employee, the same escape hatch attendance gives them.
    """
    ids = {getattr(w, "pk", w) for w in workers}
    assigned = set(
        ProjectWorker.objects.filter(project=project, worker_id__in=ids).values_list(
            "worker_id", flat=True
        )
    )
    missing = [w for w in workers if getattr(w, "pk", w) not in assigned]
    if missing:
        names = ", ".join(getattr(w, "full_name", str(w)) for w in missing)
        raise BusinessError(
            detail=f"{names} not assigned to {project.project_number}.",
            code="WORKER_NOT_ON_PROJECT",
        )


def get_visible_permits(user, supervisor):
    """Permits the user may see.

    A supervisor's view is limited to the projects they are assigned to.
    """
    qs = WorkPermit.objects.prefetch_related("workers").select_related("project", "recorded_by")
    if is_admin(user):
        return qs
    return qs.filter(project_id__in=supervised_project_ids(supervisor))


def assert_date_allowed(date):
    """Permits are a daily log: today, or up to the allowed days back."""
    today = today_in_permits_tz()
    if date > today:
        raise BusinessError(
            detail="A work permit cannot be raised for a future date.",
            code="PERMIT_FUTURE_DATE",
        )
    if date < earliest_allowed_date():
        raise BusinessError(
            detail=(
                "A work permit can only be raised for today or the previous "
                f"{max_backdate_days_text()} days."
            ),
            code="PERMIT_TOO_OLD",
        )


def max_backdate_days_text():
    from apps.permits.models import max_backdate_days

    return max_backdate_days()


def _assert_workers_free(workers, project, date, exclude_permit_pk=None):
    """Each worker may be on at most one permit for the same project + day."""
    ids = {getattr(w, "pk", w) for w in workers}
    clash = WorkPermit.objects.filter(project=project, date=date, workers__id__in=ids)
    if exclude_permit_pk is not None:
        clash = clash.exclude(pk=exclude_permit_pk)
    offenders = clash.values_list("workers__id", flat=True).distinct()
    if offenders:
        raise BusinessError(
            detail=(
                f"{worker_for_offence(offenders)} is already on a work permit "
                f"for {project.project_number} on {date}."
            ),
            code="PERMIT_ALREADY_RECORDED",
        )


def worker_for_offence(offender_ids):
    """Names of workers already permitted elsewhere on that project + day."""
    return ", ".join(
        WorkerProfile.objects.filter(pk__in=offender_ids).values_list("full_name", flat=True)
    )


def _resolve_project(project_id):
    try:
        return Project.objects.get(pk=project_id)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise ResourceNotFound(detail="Project does not exist.", code="PROJECT_NOT_FOUND")


def _resolve_worker(worker_id):
    try:
        return WorkerProfile.objects.get(pk=worker_id)
    except (WorkerProfile.DoesNotExist, ValueError, TypeError):
        raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")


def _workers_from_ids(worker_ids):
    return list(WorkerProfile.objects.filter(pk__in=worker_ids))


@transaction.atomic
def create_permit(*, actor, supervisor, project_id, workers, validated_data):
    """Raise one TBM & work-permit record for one project + one or more workers."""
    project = _resolve_project(project_id)
    workers = list(workers or [])
    if not workers:
        raise BusinessError(
            detail="At least one worker must be named on the work permit.",
            code="NO_WORKERS_SELECTED",
        )

    assert_can_manage(actor, supervisor, project.pk)
    if not is_admin(actor):
        assert_workers_assigned_to_project(workers, project)

    date = validated_data["date"]
    assert_date_allowed(date)
    _assert_workers_free(workers, project, date)

    # The write serializer turns `workers` into model instances, so they must
    # be set after create, not passed as a create() kwarg.
    fields = {key: value for key, value in validated_data.items() if key != "workers"}
    record = WorkPermit.objects.create(
        project=project,
        recorded_by=actor if getattr(actor, "is_authenticated", False) else None,
        **fields,
    )
    record.workers.set(workers)
    return record


@transaction.atomic
def update_permit(*, actor, supervisor, record, validated_data):
    """Update a permit. Scope is re-checked against the *new* project too."""
    project_ref = validated_data.get("project")
    project = project_ref if project_ref is not None else record.project
    workers_ref = validated_data.get("workers")
    new_workers = list(workers_ref) if workers_ref is not None else list(record.workers.all())

    assert_can_manage(actor, supervisor, project.pk)
    if not is_admin(actor):
        assert_workers_assigned_to_project(new_workers, project)

    date = validated_data.get("date", record.date)
    assert_date_allowed(date)
    _assert_workers_free(new_workers, project, date, exclude_permit_pk=record.pk)

    for field, value in validated_data.items():
        if field != "workers":
            setattr(record, field, value)
    if workers_ref is not None:
        record.workers.set(new_workers)
    record.save()
    return record


@transaction.atomic
def delete_permit(*, actor, record):
    """Delete a permit. Admin-only; the view enforces that."""
    record.delete()
