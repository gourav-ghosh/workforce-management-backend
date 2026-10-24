"""PPE workflows: issue and return."""

import logging
from datetime import date

from django.db import IntegrityError, transaction

from apps.audit.services import record_audit
from apps.common.exceptions import BusinessError, ResourceNotFound
from apps.common.validators import validate_image_file
from apps.ppe.models import PPE, PPEAssignment, PPEMedia
from apps.workers.models import WorkerProfile

logger = logging.getLogger(__name__)


def _assert_deletable(ppe_item):
    if ppe_item.assignments.exists():
        raise BusinessError(
            detail="PPE item has assignment history and cannot be deleted.",
            code="RESOURCE_HAS_HISTORY",
        )


@transaction.atomic
def issue_ppe(
    *,
    actor,
    ppe_id,
    worker_id,
    issue_date=None,
    expected_return_date=None,
    issue_condition=None,
    remarks="",
    media_files=None,
):
    try:
        ppe_item = PPE.objects.select_for_update().get(pk=ppe_id)
    except PPE.DoesNotExist:
        raise ResourceNotFound(detail="PPE item does not exist.", code="PPE_NOT_FOUND")

    if ppe_item.availability_status != PPE.AvailabilityStatus.AVAILABLE:
        raise BusinessError(
            detail=f"PPE item is not available (current status: {ppe_item.availability_status}).",
            code="PPE_NOT_AVAILABLE",
        )

    try:
        worker = WorkerProfile.objects.get(pk=worker_id)
    except WorkerProfile.DoesNotExist:
        raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")

    effective_issue_date = issue_date or date.today()
    if expected_return_date and expected_return_date < effective_issue_date:
        raise BusinessError(
            detail="Expected return date must be on or after the issue date.",
            code="INVALID_DATE_RANGE",
        )

    # Decrement available quantity if there are available items
    if ppe_item.available_quantity > 0:
        ppe_item.available_quantity -= 1
        if ppe_item.available_quantity == 0:
            ppe_item.availability_status = PPE.AvailabilityStatus.ASSIGNED
    elif ppe_item.total_quantity == 0:
        # First time issuing this PPE type - mark as assigned
        ppe_item.availability_status = PPE.AvailabilityStatus.ASSIGNED

    ppe_item.save(update_fields=["available_quantity", "availability_status", "updated_at"])

    try:
        assignment = PPEAssignment.objects.create(
            ppe=ppe_item,
            worker=worker,
            issue_date=effective_issue_date,
            expected_return_date=expected_return_date,
            issue_condition=issue_condition or ppe_item.condition,
            remarks=remarks,
        )
    except IntegrityError:
        raise BusinessError(
            detail="PPE item was assigned concurrently; please refresh.",
            code="PPE_NOT_AVAILABLE",
        )

    for uploaded in media_files or []:
        validate_image_file(uploaded)
        PPEMedia.objects.create(
            ppe=ppe_item,
            assignment=assignment,
            media_type=PPEMedia.MediaType.ISSUE,
            file=uploaded,
        )

    record_audit(
        action="PPE_ISSUED",
        entity=assignment,
        actor=actor,
        metadata={
            "ppe_id": ppe_item.pk,
            "ppe_code": ppe_item.ppe_id,
            "worker_id": worker.pk,
            "employee_id": worker.employee_id,
            "issue_date": str(assignment.issue_date),
        },
    )
    logger.info("PPE %s issued to worker %s", ppe_item.ppe_id, worker.employee_id)
    return assignment


@transaction.atomic
def return_ppe(*, actor, ppe_id, return_condition, return_date=None, remarks="", media_files=None, worker_id=None):
    try:
        ppe_item = PPE.objects.select_for_update().get(pk=ppe_id)
    except PPE.DoesNotExist:
        raise ResourceNotFound(detail="PPE item does not exist.", code="PPE_NOT_FOUND")

    qs = ppe_item.assignments.select_for_update().filter(status=PPEAssignment.Status.ACTIVE)
    if worker_id is not None:
        qs = qs.filter(worker_id=worker_id)
    assignment = qs.first()
    if not assignment:
        raise BusinessError(
            detail="PPE item has no active assignment to return.",
            code="NO_ACTIVE_ASSIGNMENT",
        )

    effective_return_date = return_date or date.today()
    assignment.return_date = effective_return_date
    assignment.return_condition = return_condition
    if remarks:
        assignment.remarks = remarks
    assignment.status = PPEAssignment.Status.RETURNED
    assignment.save()

    # Increment available quantity on return
    ppe_item.available_quantity = min(ppe_item.available_quantity + 1, ppe_item.total_quantity or 1)
    if ppe_item.available_quantity < ppe_item.total_quantity:
        ppe_item.availability_status = PPE.AvailabilityStatus.AVAILABLE
    elif ppe_item.available_quantity >= (ppe_item.total_quantity or 1):
        ppe_item.availability_status = PPE.AvailabilityStatus.AVAILABLE

    for uploaded in media_files or []:
        validate_image_file(uploaded)
        PPEMedia.objects.create(
            ppe=ppe_item,
            assignment=assignment,
            media_type=PPEMedia.MediaType.RETURN,
            file=uploaded,
        )

    ppe_item.condition = return_condition
    if return_condition == PPE.Condition.DAMAGED:
        ppe_item.availability_status = PPE.AvailabilityStatus.DAMAGED
    else:
        ppe_item.availability_status = PPE.AvailabilityStatus.AVAILABLE
    ppe_item.save(update_fields=["available_quantity", "condition", "availability_status"])

    record_audit(
        action="PPE_RETURNED",
        entity=assignment,
        actor=actor,
        metadata={
            "ppe_id": ppe_item.pk,
            "worker_id": assignment.worker_id,
            "return_date": str(effective_return_date),
            "return_condition": return_condition,
        },
    )
    return assignment


@transaction.atomic
def update_ppe_status(*, actor, ppe_item, new_status):
    current = ppe_item.availability_status
    if current == PPE.AvailabilityStatus.ASSIGNED:
        has_active = ppe_item.assignments.filter(status=PPEAssignment.Status.ACTIVE).exists()
        if has_active and new_status == PPE.AvailabilityStatus.AVAILABLE:
            raise BusinessError(
                detail="Record the PPE return before marking it available.",
                code="PPE_CURRENTLY_ASSIGNED",
            )
    ppe_item.availability_status = new_status
    ppe_item.save(update_fields=["availability_status", "updated_at"])
    record_audit(
        action="PPE_STATUS_CHANGED",
        entity=ppe_item,
        actor=actor,
        metadata={"from": current, "to": new_status},
    )
    return ppe_item


@transaction.atomic
def delete_ppe(*, actor, ppe_item):
    _assert_deletable(ppe_item)
    record_audit(
        action="PPE_DELETED",
        entity_type="PPE",
        entity_id=str(ppe_item.pk),
        actor=actor,
        metadata={"ppe_code": ppe_item.ppe_id},
    )
    ppe_item.delete()
