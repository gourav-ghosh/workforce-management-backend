"""Worker business workflows."""

import logging

from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from apps.accounts.models import User
from apps.audit.services import record_audit
from apps.common.exceptions import BusinessError
from apps.workers.models import WorkerProfile

logger = logging.getLogger(__name__)


def _user_has_assignments(user):
    return (
        user.worker_profile.project_assignments.exists()
        or user.worker_profile.tool_assignments.exists()
        or user.worker_profile.ppe_assignments.exists()
        or user.worker_profile.vehicle_assignments_driven.exists()
        or user.worker_profile.vehicle_assignments.exists()
    )


@transaction.atomic
def create_worker(*, actor, validated_data):
    account_username = validated_data.pop("username")
    account_password = validated_data.pop("password")
    account_email = validated_data.pop("email", "")

    validate_password(account_password)

    user = User(username=account_username, email=account_email, role=User.Role.WORKER)
    user.set_password(account_password)
    user.full_clean(exclude=["email"])
    user.save()

    worker = WorkerProfile.objects.create(user=user, **validated_data)

    record_audit(
        action="WORKER_CREATED",
        entity=worker,
        actor=actor,
        metadata={"employee_id": worker.employee_id},
    )
    logger.info("Worker created id=%s by user=%s", worker.pk, actor.pk)
    return worker


@transaction.atomic
def update_worker(*, actor, worker, validated_data):
    validated_data.pop("username", None)
    validated_data.pop("password", None)
    validated_data.pop("email", None)

    for field, value in validated_data.items():
        setattr(worker, field, value)
    worker.save()

    # Keep the login account in sync with employment status.
    new_status = validated_data.get("employment_status")
    if new_status:
        should_be_active = new_status == WorkerProfile.EmploymentStatus.ACTIVE
        if worker.user.is_active != should_be_active:
            worker.user.is_active = should_be_active
            worker.user.save(update_fields=["is_active"])

    record_audit(
        action="WORKER_UPDATED",
        entity=worker,
        actor=actor,
        metadata={k: str(v) for k, v in validated_data.items() if k != "profile_photo"},
    )
    return worker


@transaction.atomic
def set_worker_password(*, actor, worker, new_password):
    validate_password(new_password)
    worker.user.set_password(new_password)
    worker.user.save(update_fields=["password"])
    record_audit(
        action="WORKER_PASSWORD_RESET",
        entity=worker,
        actor=actor,
    )


@transaction.atomic
def delete_worker(*, actor, worker):
    if _user_has_assignments(worker.user):
        raise BusinessError(
            detail=(
                "Worker has assignment history and cannot be deleted. "
                "Set the employment status to INACTIVE instead."
            ),
            code="RESOURCE_HAS_HISTORY",
        )
    record_audit(
        action="WORKER_DELETED",
        entity_type="WorkerProfile",
        entity_id=str(worker.pk),
        actor=actor,
        metadata={"employee_id": worker.employee_id},
    )
    worker.user.delete()
