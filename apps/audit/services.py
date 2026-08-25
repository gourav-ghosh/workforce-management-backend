"""Audit recording service."""

from apps.audit.models import AuditLog


def record_audit(
    *, action, entity=None, entity_type=None, entity_id=None, actor=None, metadata=None
):
    """Persist an audit record.

    ``entity`` may be any model instance; its class name and pk are used when
    explicit values are not provided.
    """
    if entity is not None:
        entity_type = entity_type or type(entity).__name__
        entity_id = entity_id or str(entity.pk)

    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity_type=entity_type or "",
        entity_id=entity_id or "",
        metadata=metadata or {},
    )
