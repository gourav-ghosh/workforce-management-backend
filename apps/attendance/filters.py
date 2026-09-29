"""Attendance list filtering."""

import django_filters

from apps.attendance.models import AttendanceRecord


class AttendanceFilter(django_filters.FilterSet):
    worker = django_filters.NumberFilter(field_name="worker_id")
    project = django_filters.NumberFilter(field_name="project_id")
    date = django_filters.DateFilter()
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")
    is_open = django_filters.BooleanFilter(method="filter_is_open")

    class Meta:
        model = AttendanceRecord
        fields = ["worker", "project", "date"]

    def filter_is_open(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(punch_out__isnull=value)
