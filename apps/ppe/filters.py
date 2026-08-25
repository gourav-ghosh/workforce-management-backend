"""PPE list filtering."""

import django_filters

from apps.ppe.models import PPE


class PPEFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="availability_status")
    ppe_type = django_filters.CharFilter(field_name="ppe_type")
    assigned_worker = django_filters.NumberFilter(method="filter_assigned_worker")

    class Meta:
        model = PPE
        fields = ["status", "ppe_type"]

    def filter_assigned_worker(self, queryset, name, value):
        return queryset.filter(assignments__status="ACTIVE", assignments__worker_id=value)
