"""Work-permit list filtering."""

import django_filters

from apps.permits.models import WorkPermit


class WorkPermitFilter(django_filters.FilterSet):
    worker = django_filters.NumberFilter(field_name="worker_id")
    project = django_filters.NumberFilter(field_name="project_id")
    date = django_filters.DateFilter()
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")
    has_tbm_sheet = django_filters.BooleanFilter(field_name="tbm_sheet")
    has_work_permit_sheet = django_filters.BooleanFilter(field_name="work_permit_sheet")

    class Meta:
        model = WorkPermit
        fields = ["worker", "project", "date"]
