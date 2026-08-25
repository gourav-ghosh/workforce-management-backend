"""Worker list filtering."""

import django_filters

from apps.common.exceptions import BusinessError  # noqa: F401
from apps.workers.models import WorkerProfile


class WorkerFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="employment_status")
    designation = django_filters.CharFilter(field_name="designation", lookup_expr="icontains")

    class Meta:
        model = WorkerProfile
        fields = ["status", "designation"]
