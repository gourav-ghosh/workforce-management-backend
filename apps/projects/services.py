"""Project workflows: worker assignment with preserved history."""

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_audit
from apps.common.exceptions import BusinessError, ResourceNotFound
from apps.projects.models import ProjectWorker
from apps.workers.models import WorkerProfile


def _assert_deletable(project):
    has_history = (
        project.worker_assignments.exists()
        or project.tool_assignments.exists()
        or project.vehicle_assignments.exists()
    )
    if has_history:
        raise BusinessError(
            detail="Project has assignment history and cannot be deleted.",
            code="RESOURCE_HAS_HISTORY",
        )


@transaction.atomic
def assign_worker_to_project(*, actor, project, worker_id):
    try:
        worker = WorkerProfile.objects.get(pk=worker_id)
    except WorkerProfile.DoesNotExist:
        raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")

    already_active = ProjectWorker.objects.filter(
        project=project, worker=worker, is_active=True
    ).exists()
    if already_active:
        raise BusinessError(
            detail="Worker is already assigned to this project.",
            code="WORKER_ALREADY_ASSIGNED",
        )

    assignment = ProjectWorker.objects.create(project=project, worker=worker, created_by=actor)
    record_audit(
        action="WORKER_ASSIGNED_TO_PROJECT",
        entity=assignment,
        actor=actor,
        metadata={
            "project_id": project.pk,
            "project_number": project.project_number,
            "worker_id": worker.pk,
            "employee_id": worker.employee_id,
        },
    )
    return assignment


@transaction.atomic
def unassign_worker_from_project(*, actor, project, worker_id):
    assignment = (
        ProjectWorker.objects.select_for_update()
        .filter(project=project, worker_id=worker_id, is_active=True)
        .first()
    )
    if not assignment:
        raise BusinessError(
            detail="No active assignment for this worker on the project.",
            code="ASSIGNMENT_NOT_FOUND",
        )
    assignment.is_active = False
    assignment.unassigned_at = timezone.now()
    assignment.save(update_fields=["is_active", "unassigned_at", "updated_at"])
    record_audit(
        action="WORKER_UNASSIGNED_FROM_PROJECT",
        entity=assignment,
        actor=actor,
        metadata={"project_id": project.pk, "worker_id": int(worker_id)},
    )
    return assignment


@transaction.atomic
def delete_project(*, actor, project):
    _assert_deletable(project)
    record_audit(
        action="PROJECT_DELETED",
        entity_type="Project",
        entity_id=str(project.pk),
        actor=actor,
        metadata={"project_number": project.project_number},
    )
    project.delete()
