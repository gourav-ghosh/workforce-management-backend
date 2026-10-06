"""TBM & work-permit serializers."""

from rest_framework import serializers

from apps.common.validators import validate_document_file
from apps.permits.models import WorkPermit


class _WorkerBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    employee_id = serializers.CharField()
    full_name = serializers.CharField()
    designation = serializers.CharField(allow_blank=True)


class _ProjectBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    project_number = serializers.CharField()
    project_name = serializers.CharField()


class WorkPermitSerializer(serializers.ModelSerializer):
    """Read shape, with absolute URLs for whichever sheets were attached."""

    worker_detail = _WorkerBriefSerializer(source="worker", read_only=True)
    project_detail = _ProjectBriefSerializer(source="project", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()
    has_tbm_sheet = serializers.BooleanField(read_only=True)
    has_work_permit_sheet = serializers.BooleanField(read_only=True)
    attachment_count = serializers.IntegerField(read_only=True)
    tbm_sheet_url = serializers.SerializerMethodField()
    work_permit_sheet_url = serializers.SerializerMethodField()

    class Meta:
        model = WorkPermit
        fields = (
            "id",
            "project",
            "project_detail",
            "worker",
            "worker_detail",
            "date",
            "work_permit_number",
            "tbm_sheet_url",
            "work_permit_sheet_url",
            "has_tbm_sheet",
            "has_work_permit_sheet",
            "attachment_count",
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

    def _abs(self, field):
        request = self.context.get("request")
        value = getattr(self.instance, field, None) if self.instance else None
        if value and request:
            return request.build_absolute_uri(value.url)
        return None

    def get_tbm_sheet_url(self, obj):
        return self._abs("tbm_sheet")

    def get_work_permit_sheet_url(self, obj):
        return self._abs("work_permit_sheet")


class WorkPermitWriteSerializer(serializers.ModelSerializer):
    """Write shape. Sheets are optional; the permit number is not."""

    class Meta:
        model = WorkPermit
        fields = (
            "project",
            "worker",
            "date",
            "work_permit_number",
            "tbm_sheet",
            "work_permit_sheet",
            "notes",
        )
        extra_kwargs = {
            "project": {"required": False},
            "worker": {"required": False},
            "work_permit_number": {"required": False},
            # FileField takes allow_null but not allow_blank; an omitted or
            # explicitly null sheet is how "no attachment" is expressed.
            "tbm_sheet": {"required": False, "allow_null": True},
            "work_permit_sheet": {"required": False, "allow_null": True},
            "notes": {"required": False, "allow_blank": True},
        }

    def get_unique_together_validators(self):
        """Let the service own the uniqueness rule.

        DRF would otherwise answer a generic 400; the service raises a 409 with
        code PERMIT_ALREADY_RECORDED, which the clients can act on.
        """
        return []

    def validate_work_permit_number(self, value):
        if value is None or not str(value).strip():
            raise serializers.ValidationError("Work permit number is required.")
        return str(value).strip()

    def validate_tbm_sheet(self, value):
        if value:
            validate_document_file(value)
        return value

    def validate_work_permit_sheet(self, value):
        if value:
            validate_document_file(value)
        return value

    def validate(self, attrs):
        # Report every missing required field at once instead of failing on
        # whichever happens to come first.
        values = {**self._current(), **attrs}
        missing = {
            field: "This field is required."
            for field in ("project", "worker", "work_permit_number")
            if not values.get(field)
        }
        if missing:
            raise serializers.ValidationError(missing)
        return attrs

    def _current(self):
        """The stored values, so a PATCH only requires the fields it sends."""
        if self.instance is None:
            return {}
        return {
            "project": self.instance.project_id,
            "worker": self.instance.worker_id,
            "work_permit_number": self.instance.work_permit_number,
        }
