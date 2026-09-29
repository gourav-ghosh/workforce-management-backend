"""Attendance serializers."""

from django.utils import timezone
from rest_framework import serializers

from apps.attendance.models import (
    AttendanceRecord,
    attendance_timezone,
)


class _WorkerBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    employee_id = serializers.CharField()
    full_name = serializers.CharField()
    designation = serializers.CharField(allow_blank=True)


class _ProjectBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    project_number = serializers.CharField()
    project_name = serializers.CharField()


class AttendanceRecordSerializer(serializers.ModelSerializer):
    """Read shape. Late flag and hours are derived, never stored."""

    worker_detail = _WorkerBriefSerializer(source="worker", read_only=True)
    project_detail = _ProjectBriefSerializer(source="project", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()
    is_late = serializers.BooleanField(read_only=True)
    late_by_minutes = serializers.IntegerField(read_only=True)
    work_hours = serializers.FloatField(read_only=True, allow_null=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = (
            "id",
            "worker",
            "worker_detail",
            "project",
            "project_detail",
            "date",
            "punch_in",
            "punch_out",
            "work_hours",
            "is_late",
            "late_by_minutes",
            "is_open",
            "notes",
            "recorded_by",
            "recorded_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_recorded_by_name(self, obj):
        if not obj.recorded_by:
            return None
        return obj.recorded_by.mobile_number


class AttendanceRecordWriteSerializer(serializers.ModelSerializer):
    """Write shape. `recorded_by` is always set from the request user."""

    class Meta:
        model = AttendanceRecord
        fields = ("worker", "project", "date", "punch_in", "punch_out", "notes")
        extra_kwargs = {
            # An admin may log attendance with no project at all; a
            # supervisor is required to pick one (enforced in the service).
            "project": {"required": False, "allow_null": True},
            "punch_out": {"required": False, "allow_null": True},
            "notes": {"required": False, "allow_blank": True},
        }

    def get_unique_together_validators(self):
        """Let the service own the uniqueness rule.

        DRF would otherwise auto-add a UniqueTogetherValidator for
        (worker, project, date) and answer a generic 400. The service raises
        a 409 with code ATTENDANCE_ALREADY_RECORDED, which the clients can
        act on, so the validator is suppressed here.
        """
        return []

    def _local_date(self, value):
        """The calendar date [value] falls on, in the attendance timezone."""
        if value is None:
            return None
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone=attendance_timezone())
        return timezone.localtime(value, attendance_timezone()).date()

    def validate(self, attrs):
        instance = self.instance
        date = attrs.get("date", instance.date if instance else None)
        punch_in = attrs.get("punch_in", instance.punch_in if instance else None)
        punch_out = attrs.get("punch_out", instance.punch_out if instance else None)

        if punch_in and punch_out and punch_out <= punch_in:
            raise serializers.ValidationError({"punch_out": "Punch-out must be after punch-in."})

        # `date` is the working day, and the late flag plus worked hours are
        # both derived from it. A punch-in sent for a different calendar day
        # would silently produce nonsense (a 25-hour "late" figure), so the
        # timestamps must belong to the working date. This matters most when
        # backdating, where the client's clock and the chosen day differ.
        if date is not None:
            for field, moment in (("punch_in", punch_in), ("punch_out", punch_out)):
                local = self._local_date(moment)
                if local is not None and local != date:
                    raise serializers.ValidationError(
                        {
                            field: (
                                f"{field.replace('_', ' ').capitalize()} is on {local} "
                                f"but the working date is {date}."
                            )
                        }
                    )
        return attrs
