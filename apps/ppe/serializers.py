"""PPE serializers."""

from rest_framework import serializers

from apps.common.validators import validate_image_file
from apps.ppe.models import PPE, PPEAssignment, PPEMedia


class PPEListSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()
    expired = serializers.SerializerMethodField()

    class Meta:
        model = PPE
        fields = (
            "id",
            "ppe_id",
            "ppe_type",
            "name",
            "size",
            "condition",
            "availability_status",
            "expired",
            "photo_url",
        )

    def get_photo_url(self, obj):
        request = self.context.get("request")
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        return None

    def get_expired(self, obj):
        from django.utils import timezone

        return bool(obj.expiry_date and obj.expiry_date < timezone.localdate())


class CurrentPPEAssignmentSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.full_name", read_only=True)
    employee_id = serializers.CharField(source="worker.employee_id", read_only=True)

    class Meta:
        model = PPEAssignment
        fields = (
            "id",
            "worker_name",
            "employee_id",
            "issue_date",
            "expected_return_date",
            "issue_condition",
        )


class PPEDetailSerializer(PPEListSerializer):
    current_assignment = serializers.SerializerMethodField()

    class Meta(PPEListSerializer.Meta):
        fields = PPEListSerializer.Meta.fields + (
            "category",
            "purchase_date",
            "expiry_date",
            "remarks",
            "current_assignment",
            "created_at",
            "updated_at",
        )

    def get_current_assignment(self, obj):
        assignment = obj.assignments.select_related("worker").filter(status="ACTIVE").first()
        return CurrentPPEAssignmentSerializer(assignment).data if assignment else None


class PPEWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PPE
        fields = (
            "id",
            "ppe_id",
            "ppe_type",
            "name",
            "category",
            "size",
            "photo",
            "purchase_date",
            "expiry_date",
            "condition",
            "availability_status",
            "remarks",
        )
        extra_kwargs = {
            "ppe_id": {"required": False},
            "name": {"required": False},
            "ppe_type": {"required": False},
            "availability_status": {"required": False},
        }

    def validate_photo(self, value):
        if value:
            validate_image_file(value)
        return value

    def validate(self, attrs):
        creating = self.instance is None
        if creating:
            for required in ("ppe_id", "name", "ppe_type"):
                if not attrs.get(required):
                    raise serializers.ValidationError({required: "This field is required."})
        if attrs.get("ppe_type") and attrs["ppe_type"] not in PPE.PPEType.values:
            raise serializers.ValidationError({"ppe_type": "Invalid PPE type."})
        purchase = attrs.get(
            "purchase_date", self.instance.purchase_date if self.instance else None
        )
        expiry = attrs.get("expiry_date", self.instance.expiry_date if self.instance else None)
        if purchase and expiry and expiry < purchase:
            raise serializers.ValidationError(
                {"expiry_date": "Expiry date must be after the purchase date."}
            )
        return attrs


class PPEIssueSerializer(serializers.Serializer):
    worker_id = serializers.IntegerField()
    issue_date = serializers.DateField(required=False)
    expected_return_date = serializers.DateField(required=False, allow_null=True)
    issue_condition = serializers.ChoiceField(
        choices=PPE.Condition.choices, required=False, allow_null=True
    )
    remarks = serializers.CharField(required=False, allow_blank=True, default="")
    photos = serializers.ListField(child=serializers.ImageField(), required=False, write_only=True)


class PPEReturnSerializer(serializers.Serializer):
    return_condition = serializers.ChoiceField(choices=PPE.Condition.choices)
    return_date = serializers.DateField(required=False)
    remarks = serializers.CharField(required=False, allow_blank=True, default="")
    photos = serializers.ListField(child=serializers.ImageField(), required=False, write_only=True)


class PPEHistorySerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.full_name", read_only=True)
    employee_id = serializers.CharField(source="worker.employee_id", read_only=True)

    class Meta:
        model = PPEAssignment
        fields = (
            "id",
            "worker_name",
            "employee_id",
            "issue_date",
            "expected_return_date",
            "return_date",
            "issue_condition",
            "return_condition",
            "status",
            "remarks",
        )


class PPEMediaSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = PPEMedia
        fields = ("id", "media_type", "file_url", "assignment", "created_at")

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class PPEMediaUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PPEMedia
        fields = ("file", "media_type")

    def validate_file(self, value):
        validate_image_file(value)
        return value
