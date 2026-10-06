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


def assert_worker_assigned_to_project(worker, project):
    """A supervisor's permit must belong to a worker on that project.

    Admins are deliberately not checked: they may record a permit for any
    employee, the same escape hatch attendance gives them.
    """
    if not ProjectWorker.objects.filter(project=project, worker=worker).exists():
        raise BusinessError(
            detail=f"{worker.full_name} is not assigned to {project.project_number}.",
            code="WORKER_NOT_ON_PROJECT",
        )


def get_visible_permits(user, supervisor):
    """Permits the user may see.

    A supervisor's view is limited to the projects they are assigned to.
    """
    qs = WorkPermit.objects.select_related("worker", "project", "recorded_by")
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


def _assert_unique(project, worker, date, exclude_pk=None):
    clash = WorkPermit.objects.filter(project=project, worker=worker, date=date)
    if exclude_pk is not None:
        clash = clash.exclude(pk=exclude_pk)
    if clash.exists():
        raise BusinessError(
            detail=(
                f"A work permit for {worker.full_name} on {project.project_number} "
                f"({date}) is already recorded."
            ),
            code="PERMIT_ALREADY_RECORDED",
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


@transaction.atomic
def create_permit(*, actor, supervisor, project_id, worker_id, validated_data):
    """Raise one TBM & work-permit record after validating scope and assignment."""
    project = _resolve_project(project_id)
    worker = _resolve_worker(worker_id)

    assert_can_manage(actor, supervisor, project.pk)
    if not is_admin(actor):
        assert_worker_assigned_to_project(worker, project)

    date = validated_data["date"]
    assert_date_allowed(date)
    _assert_unique(project, worker, date)

    # The write serializer hands back model instances for worker/project, so
    # drop them before create() to avoid duplicate kwargs.
    fields = {
        key: value for key, value in validated_data.items() if key not in ("worker", "project")
    }
    record = WorkPermit.objects.create(
        project=project,
        worker=worker,
        recorded_by=actor if getattr(actor, "is_authenticated", False) else None,
        **fields,
    )
    return record


@transaction.atomic
def update_permit(*, actor, supervisor, record, validated_data):
    """Update a permit. Scope is re-checked against the *new* project too."""
    project_ref = validated_data.get("project")
    project = project_ref if project_ref is not None else record.project
    worker_ref = validated_data.get("worker")
    worker = worker_ref if worker_ref is not None else record.worker

    assert_can_manage(actor, supervisor, project.pk)
    if not is_admin(actor):
        assert_worker_assigned_to_project(worker, project)

    date = validated_data.get("date", record.date)
    assert_date_allowed(date)
    _assert_unique(project, worker, date, exclude_pk=record.pk)

    for field, value in validated_data.items():
        setattr(record, field, value)
    record.save()
    return record


@transaction.atomic
def delete_permit(*, actor, record):
    """Delete a permit. Admin-only; the view enforces that."""
    record.delete()
