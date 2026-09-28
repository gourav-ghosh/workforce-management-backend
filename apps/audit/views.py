"""Audit log read API (admin only)."""

import django_filters
from rest_framework import serializers
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.common.pagination import DefaultPagination
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
        parts = value.split("#")
        if len(parts) == 2:
            return queryset.filter(entity_type__iexact=parts[0], entity_id=parts[1])
        return queryset.filter(entity_id=value)


class AuditLogListView(APIView):
    """GET /audit/ — list audit log entries (admin only)."""

    permission_classes = [IsAdminRole]
    pagination_class = DefaultPagination
    filterset_class = AuditLogFilter

    def get(self, request):
        qs = AuditLog.objects.select_related("actor").all()
        qs = self.filterset_class(request.GET, queryset=qs).qs
        ordering = request.query_params.get("ordering", "-created_at")
        qs = qs.order_by(ordering)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = AuditLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
