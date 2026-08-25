"""Project list filtering."""

import django_filters

from apps.projects.models import Project


class ProjectFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    measurement_sheet_status = django_filters.CharFilter(field_name="measurement_sheet_status")

    class Meta:
        model = Project
        fields = ["status", "measurement_sheet_status"]
