"""Employee Performance workflows."""

import logging

from django.db import transaction

from apps.audit.services import record_audit
from apps.common.exceptions import ResourceNotFound
from apps.performance.models import PerformanceRecord
from apps.workers.models import WorkerProfile

logger = logging.getLogger(__name__)


@transaction.atomic
def create_performance_record(*, actor, validated_data):
    worker_id = validated_data.pop("worker").pk
    try:
        worker = WorkerProfile.objects.get(pk=worker_id)
    except WorkerProfile.DoesNotExist:
        raise ResourceNotFound(detail="Worker does not exist.", code="WORKER_NOT_FOUND")

    record = PerformanceRecord.objects.create(evaluator=actor, worker=worker, **validated_data)
    record_audit(
        action="PERFORMANCE_RECORD_CREATED",
        entity=record,
        actor=actor,
        metadata={
            "worker_id": worker.pk,
            "period_start": str(record.period_start),
            "period_end": str(record.period_end),
        },
    )
    return record


@transaction.atomic
def update_performance_record(*, actor, record, validated_data):
    validated_data.pop("worker", None)
    for field, value in validated_data.items():
        setattr(record, field, value)
    record.save()
    record_audit(
        action="PERFORMANCE_RECORD_UPDATED",
        entity=record,
        actor=actor,
    )
    return record


@transaction.atomic
def delete_performance_record(*, actor, record):
    record_audit(
        action="PERFORMANCE_RECORD_DELETED",
        entity_type="PerformanceRecord",
        entity_id=str(record.pk),
        actor=actor,
        metadata={"worker_id": record.worker_id},
    )
    record.delete()
