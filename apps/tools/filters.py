"""Tool list filtering."""

import django_filters

from apps.tools.models import Tool


class ToolFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="availability_status")
    category = django_filters.CharFilter(field_name="category")
    assigned_worker = django_filters.NumberFilter(method="filter_assigned_worker")

    class Meta:
        model = Tool
        fields = ["status", "category"]

    def filter_assigned_worker(self, queryset, name, value):
        return queryset.filter(assignments__status="ACTIVE", assignments__worker_id=value)
