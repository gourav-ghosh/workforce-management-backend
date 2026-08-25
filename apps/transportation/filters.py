"""Vehicle list filtering."""

import django_filters

from apps.transportation.models import Vehicle


class VehicleFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    vehicle_type = django_filters.CharFilter(field_name="vehicle_type")

    class Meta:
        model = Vehicle
        fields = ["status", "vehicle_type"]
