"""Audit log read API (admin only)."""

import django_filters
from rest_framework import serializers, viewsets

from apps.audit.models import AuditLog
from apps.common.permissions import IsAdminRole


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "actor",
            "actor_username",
            "action",
            "entity_type",
            "entity_id",
            "metadata",
            "created_at",
        )


class AuditLogFilter(django_filters.FilterSet):
    entity = django_filters.CharFilter(method="filter_entity")
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = AuditLog
        fields = ["action", "entity_type", "entity_id", "actor", "entity"]

    def filter_entity(self, queryset, name, value):
        # Convenience filter: "Tool#12" style or plain id combined with entity_type param.
        parts = value.split("#")
        if len(parts) == 2:
            return queryset.filter(entity_type__iexact=parts[0], entity_id=parts[1])
        return queryset.filter(entity_id=value)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminRole]
    serializer_class = AuditLogSerializer
    filterset_class = AuditLogFilter
    ordering_fields = ["created_at", "action"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return AuditLog.objects.select_related("actor").all()
