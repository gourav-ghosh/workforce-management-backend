"""Tool workflows: issue, return, damage — transactional with locking."""

import logging
from datetime import date

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.audit.services import record_audit
from apps.common.exceptions import BusinessError, ResourceNotFound
from apps.common.validators import validate_image_file
from apps.tools.models import Tool, ToolAssignment, ToolDamage, ToolMedia
from apps.workers.models import WorkerProfile

logger = logging.getLogger(__name__)


def _assert_deletable(tool):
    if tool.assignments.exists() or tool.damages.exists():
        raise BusinessError(
            detail="Tool has assignment/damage history and cannot be deleted.",
            code="RESOURCE_HAS_HISTORY",
        )


@transaction.atomic
def issue_tool(
    *,
    actor,
    tool_id,
    worker_id,
    project_id=None,
    issue_date=None,
    expected_return_date=None,
    issue_condition=None,
    remarks="",
    media_files=None,
):
    """Issue a tool to a worker. Only one active assignment may exist."""
    try:
        tool = Tool.objects.select_for_update().get(pk=tool_id)
    except Tool.DoesNotExist:
        raise ResourceNotFound(detail="Tool does not exist.", code="TOOL_NOT_FOUND")

    if tool.availability_status != Tool.AvailabilityStatus.AVAILABLE:
        raise BusinessError(
            detail=f"Tool is not available (current status: {tool.availability_status}).",
            code="TOOL_NOT_AVAILABLE",
        )

    try:
        worker = WorkerProfile.objects.get(pk=worker_id)
    except WorkerProfile.DoesNotExist:
        raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")

    project = None
    if project_id is not None:
        from apps.projects.models import Project

        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            raise ResourceNotFound(detail="Project does not exist.", code="PROJECT_NOT_FOUND")

    effective_issue_date = issue_date or date.today()
    if expected_return_date and expected_return_date < effective_issue_date:
        raise BusinessError(
            detail="Expected return date must be on or after the issue date.",
            code="INVALID_DATE_RANGE",
        )

    try:
        assignment = ToolAssignment.objects.create(
            tool=tool,
            worker=worker,
            project=project,
            issue_date=effective_issue_date,
            expected_return_date=expected_return_date,
            issue_condition=issue_condition or tool.condition,
            remarks=remarks,
        )
    except IntegrityError:
        # The partial unique constraint guarantees only one active
        # assignment per tool even under concurrent requests.
        raise BusinessError(
            detail="Tool was assigned concurrently; please refresh.",
            code="TOOL_NOT_AVAILABLE",
        )

    for uploaded in media_files or []:
        validate_image_file(uploaded)
        ToolMedia.objects.create(
            tool=tool,
            assignment=assignment,
            media_type=ToolMedia.MediaType.ISSUE,
            file=uploaded,
        )

    tool.availability_status = Tool.AvailabilityStatus.ASSIGNED
    tool.save(update_fields=["availability_status", "updated_at"])

    record_audit(
        action="TOOL_ISSUED",
        entity=assignment,
        actor=actor,
        metadata={
            "tool_id": tool.pk,
            "tool_code": tool.tool_id,
            "worker_id": worker.pk,
            "employee_id": worker.employee_id,
            "project_id": project.pk if project else None,
            "issue_date": str(assignment.issue_date),
        },
    )
    logger.info("Tool %s issued to worker %s", tool.tool_id, worker.employee_id)
    return assignment


@transaction.atomic
def return_tool(
    *,
    actor,
    tool_id,
    return_condition,
    return_date=None,
    remarks="",
    media_files=None,
):
    """Return a currently issued tool; status derives from return condition."""
    try:
        tool = Tool.objects.select_for_update().get(pk=tool_id)
    except Tool.DoesNotExist:
        raise ResourceNotFound(detail="Tool does not exist.", code="TOOL_NOT_FOUND")

    assignment = (
        tool.assignments.select_for_update().filter(status=ToolAssignment.Status.ACTIVE).first()
    )
    if not assignment:
        raise BusinessError(
            detail="Tool has no active assignment to return.",
            code="NO_ACTIVE_ASSIGNMENT",
        )

    effective_return_date = return_date or date.today()
    assignment.return_date = effective_return_date
    assignment.return_condition = return_condition
    if remarks:
        assignment.remarks = remarks
    assignment.status = ToolAssignment.Status.RETURNED
    assignment.save()

    for uploaded in media_files or []:
        validate_image_file(uploaded)
        ToolMedia.objects.create(
            tool=tool,
            assignment=assignment,
            media_type=ToolMedia.MediaType.RETURN,
            file=uploaded,
        )

    tool.condition = return_condition
    if return_condition == Tool.Condition.DAMAGED:
        tool.availability_status = Tool.AvailabilityStatus.DAMAGED
    else:
        tool.availability_status = Tool.AvailabilityStatus.AVAILABLE
    tool.save(update_fields=["condition", "availability_status", "updated_at"])

    record_audit(
        action="TOOL_RETURNED",
        entity=assignment,
        actor=actor,
        metadata={
            "tool_id": tool.pk,
            "worker_id": assignment.worker_id,
            "return_date": str(effective_return_date),
            "return_condition": return_condition,
        },
    )
    return assignment


@transaction.atomic
def record_tool_damage(
    *,
    actor,
    tool_id=None,
    damage_description,
    damage_condition,
    damage_date=None,
    repair_status=None,
    assignment_id=None,
    worker_profile=None,
    remarks="",
    media_files=None,
):
    """Record tool damage.

    ``tool_id`` is required for admin reports; ``assignment_id`` + an optional
    ``worker_profile`` is used when a worker reports damage against one of
    their own assignments.
    """
    assignment = None
    if assignment_id is not None:
        assignment_qs = ToolAssignment.objects.select_for_update().select_related("tool")
        if tool_id is not None:
            assignment_qs = assignment_qs.filter(tool_id=tool_id)
        assignment = assignment_qs.filter(pk=assignment_id).first()
        if not assignment:
            raise ResourceNotFound(
                detail="Assignment does not exist.", code="ASSIGNMENT_NOT_FOUND"
            )
        if worker_profile is not None and assignment.worker_id != worker_profile.pk:
            raise BusinessError(
                detail="You may only report damage against your own assignments.",
                code="WORKER_DATA_ISOLATION",
            )
        tool = assignment.tool
    else:
        if tool_id is None:
            raise BusinessError(
                detail="Either tool_id or assignment_id is required.",
                code="TOOL_NOT_FOUND",
            )
        try:
            tool = Tool.objects.select_for_update().get(pk=tool_id)
        except Tool.DoesNotExist:
            raise ResourceNotFound(detail="Tool does not exist.", code="TOOL_NOT_FOUND")

    damage = ToolDamage.objects.create(
        tool=tool,
        assignment=assignment,
        damage_date=damage_date or date.today(),
        damage_description=damage_description,
        damage_condition=damage_condition,
        repair_status=repair_status or ToolDamage.RepairStatus.REPORTED,
        remarks=remarks,
    )

    for uploaded in media_files or []:
        validate_image_file(uploaded)
        ToolMedia.objects.create(
            tool=tool,
            damage=damage,
            media_type=ToolMedia.MediaType.DAMAGE,
            file=uploaded,
        )

    if tool.availability_status in (
        Tool.AvailabilityStatus.AVAILABLE,
        Tool.AvailabilityStatus.ASSIGNED,
    ):
        tool.availability_status = Tool.AvailabilityStatus.DAMAGED
        tool.save(update_fields=["availability_status", "updated_at"])

    record_audit(
        action="TOOL_DAMAGED",
        entity=damage,
        actor=actor,
        metadata={
            "tool_id": tool.pk,
            "damage_date": str(damage.damage_date),
            "reported_by_role": "WORKER" if worker_profile is not None else "ADMIN",
        },
    )
    return damage


@transaction.atomic
def repair_tool(*, actor, tool, condition, close_assignment, notes=""):
    """Mark a damaged tool as repaired and return it to circulation.

    - Updates the tool condition.
    - Marks all open damage records as COMPLETED.
    - Optionally closes the active assignment (records a return today).
    - Sets availability to AVAILABLE once no active assignment remains.
    """
    valid = {choice for choice, _ in Tool.Condition.choices}
    if condition not in valid:
        raise ValidationError({"condition": "Invalid condition."})

    tool.condition = condition
    tool.damages.filter(repair_status=ToolDamage.RepairStatus.REPORTED).update(
        repair_status=ToolDamage.RepairStatus.COMPLETED
    )
    tool.damages.filter(repair_status=ToolDamage.RepairStatus.IN_PROGRESS).update(
        repair_status=ToolDamage.RepairStatus.COMPLETED
    )

    if close_assignment:
        active = tool.assignments.filter(status=ToolAssignment.Status.ACTIVE).first()
        if active:
            active.return_date = date.today()
            active.return_condition = condition
            if notes:
                active.remarks = (active.remarks + "\n" if active.remarks else "") + notes
            active.status = ToolAssignment.Status.RETURNED
            active.save()

    if not tool.assignments.filter(status=ToolAssignment.Status.ACTIVE).exists():
        tool.availability_status = Tool.AvailabilityStatus.AVAILABLE
    tool.save(
        update_fields=["condition", "availability_status", "updated_at"]
    )

    record_audit(
        action="TOOL_REPAIRED",
        entity=tool,
        actor=actor,
        metadata={
            "condition": condition,
            "closed_assignment": bool(close_assignment),
        },
    )
    return tool


@transaction.atomic
def update_tool_status(*, actor, tool, new_status):
    """Manual status transitions (e.g. maintenance/lost/retired)."""
    current = tool.availability_status
    if current == Tool.AvailabilityStatus.ASSIGNED:
        has_active_assignment = tool.assignments.filter(
            status=ToolAssignment.Status.ACTIVE
        ).exists()
        blocked_targets = (
            Tool.AvailabilityStatus.AVAILABLE,
            Tool.AvailabilityStatus.RETIRED,
        )
        if has_active_assignment and new_status in blocked_targets:
            raise BusinessError(
                detail="Return the tool before changing its status.",
                code="TOOL_CURRENTLY_ASSIGNED",
            )
    tool.availability_status = new_status
    tool.save(update_fields=["availability_status", "updated_at"])
    record_audit(
        action="TOOL_STATUS_CHANGED",
        entity=tool,
        actor=actor,
        metadata={"from": current, "to": new_status},
    )
    return tool


@transaction.atomic
def delete_tool(*, actor, tool):
    _assert_deletable(tool)
    record_audit(
        action="TOOL_DELETED",
        entity_type="Tool",
        entity_id=str(tool.pk),
        actor=actor,
        metadata={"tool_code": tool.tool_id},
    )
    tool.delete()
