"""Work-permit list filtering."""

import django_filters
from django.db.models import Q

from apps.permits.models import WorkPermit


class WorkPermitFilter(django_filters.FilterSet):
    worker = django_filters.NumberFilter(field_name="workers", lookup_expr="exact")
    project = django_filters.NumberFilter(field_name="project_id")
    date = django_filters.DateFilter()
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")
    has_tbm_sheet = django_filters.BooleanFilter(method="filter_has_tbm_sheet")
    has_work_permit_sheet = django_filters.BooleanFilter(method="filter_has_work_permit_sheet")

    class Meta:
        model = WorkPermit
        fields = ["worker", "project", "date"]

    def filter_has_tbm_sheet(self, queryset, name, value):
        if value is None:
            return queryset
        if value:
            return queryset.exclude(tbm_sheet__isnull=True).exclude(tbm_sheet="")
        return queryset.filter(self._no_file_q("tbm_sheet"))

    def filter_has_work_permit_sheet(self, queryset, name, value):
        if value is None:
            return queryset
        if value:
            return queryset.exclude(work_permit_sheet__isnull=True).exclude(work_permit_sheet="")
        return queryset.filter(self._no_file_q("work_permit_sheet"))

    def _no_file_q(self, field):
        return Q(**{f"{field}__isnull": True}) | Q(**{field: ""})
