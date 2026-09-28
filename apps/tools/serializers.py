"""Tool serializers."""

from rest_framework import serializers

from apps.common.validators import validate_image_file
from apps.tools.models import Tool, ToolAssignment, ToolDamage, ToolMedia


class CurrentAssignmentSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.full_name", read_only=True)
    employee_id = serializers.CharField(source="worker.employee_id", read_only=True)

    class Meta:
        model = ToolAssignment
        fields = (
            "id",
            "worker_name",
            "employee_id",
            "issue_date",
            "expected_return_date",
            "issue_condition",
        )


class ToolPhotoUrlField(serializers.SerializerMethodField):
    pass


class ToolListSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Tool
        fields = (
            "id",
            "tool_id",
            "name",
            "category",
            "condition",
            "availability_status",
            "photo_url",
        )

    def get_photo_url(self, obj):
        request = self.context.get("request")
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        return None


class ToolDetailSerializer(ToolListSerializer):
    current_assignment = serializers.SerializerMethodField()
    open_damage_count = serializers.SerializerMethodField()
    damages = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()

    class Meta(ToolListSerializer.Meta):
        fields = ToolListSerializer.Meta.fields + (
            "description",
            "purchase_date",
            "remarks",
            "current_assignment",
            "open_damage_count",
            "damages",
            "media",
            "created_at",
            "updated_at",
        )

    def get_current_assignment(self, obj):
        assignment = obj.assignments.select_related("worker").filter(status="ACTIVE").first()
        return CurrentAssignmentSerializer(assignment).data if assignment else None

    def get_open_damage_count(self, obj):
        from apps.tools.models import ToolDamage

        return obj.damages.exclude(repair_status=ToolDamage.RepairStatus.COMPLETED).count()

    def get_damages(self, obj):
        return ToolDamageReadSerializer(
            obj.damages.select_related().prefetch_related("media").all(),
            many=True,
            context=self.context,
        ).data

    def get_media(self, obj):
        return ToolMediaSerializer(
            obj.media.select_related("assignment", "damage").all(),
            many=True,
            context=self.context,
        ).data


class ToolWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tool
        fields = (
            "id",
            "tool_id",
            "name",
            "category",
            "description",
            "photo",
            "purchase_date",
            "condition",
            "availability_status",
            "remarks",
        )
        extra_kwargs = {
            "tool_id": {"required": False},
            "name": {"required": False},
            "availability_status": {"required": False},
        }

    def validate_photo(self, value):
        if value:
            validate_image_file(value)
        return value

    def validate(self, attrs):
        creating = self.instance is None
        if creating:
            for required in ("tool_id", "name"):
                if not attrs.get(required):
                    raise serializers.ValidationError({required: "This field is required."})
        new_status = attrs.get("availability_status")
        if new_status and self.instance and self.instance.availability_status != new_status:
            # Defer transition rules to service; serializer just sanity-checks.
            allowed = set(Tool.AvailabilityStatus.values)
            if new_status not in allowed:
                raise serializers.ValidationError({"availability_status": "Invalid status."})
            if (
                self.instance.availability_status == Tool.AvailabilityStatus.ASSIGNED
                and new_status in (Tool.AvailabilityStatus.AVAILABLE,)
            ):
                raise serializers.ValidationError(
                    {"availability_status": ("Return the tool before marking it available.")}
                )
        return attrs


class ToolIssueSerializer(serializers.Serializer):
    worker_id = serializers.IntegerField()
    project_id = serializers.IntegerField(required=False, allow_null=True)
    issue_date = serializers.DateField(required=False)
    expected_return_date = serializers.DateField(required=False, allow_null=True)
    issue_condition = serializers.ChoiceField(
        choices=Tool.Condition.choices, required=False, allow_null=True
    )
    remarks = serializers.CharField(required=False, allow_blank=True, default="")
    photos = serializers.ListField(
        child=serializers.ImageField(), required=False, write_only=True
    )


class ToolReturnSerializer(serializers.Serializer):
    return_condition = serializers.ChoiceField(choices=Tool.Condition.choices)
    return_date = serializers.DateField(required=False)
    remarks = serializers.CharField(required=False, allow_blank=True, default="")
    photos = serializers.ListField(child=serializers.ImageField(), required=False, write_only=True)


class ToolDamageInputSerializer(serializers.Serializer):
    assignment_id = serializers.IntegerField(required=False, allow_null=True)
    damage_date = serializers.DateField(required=False)
    damage_description = serializers.CharField()
    damage_condition = serializers.ChoiceField(choices=Tool.Condition.choices)
    repair_status = serializers.ChoiceField(choices=ToolDamage.RepairStatus.choices, required=False)
    remarks = serializers.CharField(required=False, allow_blank=True, default="")
    photos = serializers.ListField(child=serializers.ImageField(), required=False, write_only=True)


class ToolDamageReadSerializer(serializers.ModelSerializer):
    media = serializers.SerializerMethodField()

    class Meta:
        model = ToolDamage
        fields = (
            "id",
            "tool",
            "assignment",
            "damage_date",
            "damage_description",
            "damage_condition",
            "repair_status",
            "remarks",
            "media",
            "created_at",
        )

    def get_media(self, obj):
        request = self.context.get("request")
        items = []
        for media in obj.media.all():
            url = None
            if media.file and request:
                url = request.build_absolute_uri(media.file.url)
            items.append(
                {
                    "id": media.id,
                    "file_url": url,
                    "media_type": media.media_type,
                    "created_at": media.created_at,
                }
            )
        return items


class ToolHistorySerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.full_name", read_only=True)
    employee_id = serializers.CharField(source="worker.employee_id", read_only=True)
    project_number = serializers.CharField(
        source="project.project_number", read_only=True, default=None
    )
    damages = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()

    class Meta:
        model = ToolAssignment
        fields = (
            "id",
            "worker_name",
            "employee_id",
            "project_number",
            "issue_date",
            "expected_return_date",
            "return_date",
            "issue_condition",
            "return_condition",
            "status",
            "remarks",
            "damages",
            "media",
        )

    def get_damages(self, obj):
        result = []
        for d in obj.damages.all():
            media_items = []
            request = self.context.get("request")
            for m in d.media.all():
                url = None
                if m.file and request:
                    url = request.build_absolute_uri(m.file.url)
                media_items.append(
                    {
                        "id": m.id,
                        "file_url": url,
                        "media_type": m.media_type,
                        "created_at": m.created_at,
                    }
                )
            result.append(
                {
                    "id": d.id,
                    "damage_date": d.damage_date,
                    "description": d.damage_description,
                    "condition": d.damage_condition,
                    "repair_status": d.repair_status,
                    "media": media_items,
                }
            )
        return result

    def get_media(self, obj):
        request = self.context.get("request")
        items = []
        for media in obj.media.all():
            url = None
            if media.file and request:
                url = request.build_absolute_uri(media.file.url)
            items.append(
                {
                    "id": media.id,
                    "file_url": url,
                    "media_type": media.media_type,
                    "created_at": media.created_at,
                }
            )
        return items


class ToolMediaSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ToolMedia
        fields = ("id", "media_type", "file_url", "assignment", "damage", "created_at")

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class ToolMediaUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolMedia
        fields = ("file", "media_type")

    def validate_file(self, value):
        validate_image_file(value)
        return value
