"""Vehicle serializers."""

from django.utils import timezone
from rest_framework import serializers

from apps.common.validators import validate_image_file
from apps.transportation.models import (
    Vehicle,
    VehicleAssignment,
    VehicleBooking,
    VehicleMedia,
)


class VehicleListSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = (
            "id",
            "vehicle_id",
            "registration_number",
            "vehicle_type",
            "make_model",
            "status",
            "photo_url",
        )

    def get_photo_url(self, obj):
        request = self.context.get("request")
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        return None


class CurrentVehicleAssignmentSerializer(serializers.ModelSerializer):
    project_number = serializers.CharField(
        source="project.project_number", read_only=True, default=None
    )
    worker_name = serializers.CharField(source="worker.full_name", read_only=True, default=None)
    driver_name = serializers.CharField(source="driver.full_name", read_only=True, default=None)

    class Meta:
        model = VehicleAssignment
        fields = (
            "id",
            "assignment_type",
            "project_number",
            "worker_name",
            "driver_name",
            "start_datetime",
            "end_datetime",
            "purpose",
        )


class VehicleDetailSerializer(VehicleListSerializer):
    current_assignment = serializers.SerializerMethodField()

    class Meta(VehicleListSerializer.Meta):
        fields = VehicleListSerializer.Meta.fields + (
            "capacity",
            "driver",
            "insurance_valid_until",
            "inspection_valid_until",
            "rc_validity",
            "fitness_validity",
            "pollution_validity",
            "safety_validity",
            "load_test_validity",
            "yearly_maintenance_charge",
            "remarks",
            "current_assignment",
            "created_at",
            "updated_at",
        )

    def get_current_assignment(self, obj):
        now = self.context.get("now")
        from django.utils import timezone

        now = now or timezone.now()
        assignment = (
            obj.assignments.filter(end_datetime__isnull=True).order_by("-start_datetime").first()
        )
        return CurrentVehicleAssignmentSerializer(assignment).data if assignment else None


class VehicleWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = (
            "id",
            "vehicle_id",
            "registration_number",
            "vehicle_type",
            "make_model",
            "photo",
            "driver",
            "capacity",
            "status",
            "insurance_valid_until",
            "inspection_valid_until",
            "rc_validity",
            "fitness_validity",
            "pollution_validity",
            "safety_validity",
            "load_test_validity",
            "yearly_maintenance_charge",
            "remarks",
        )
        extra_kwargs = {
            "vehicle_id": {"required": False},
            "registration_number": {"required": False},
            "vehicle_type": {"required": False},
            "status": {"required": False},
        }

    def validate_photo(self, value):
        if value:
            validate_image_file(value)
        return value

    def validate_registration_number(self, value):
        return value.upper()

    def validate(self, attrs):
        creating = self.instance is None
        if creating:
            for required in ("vehicle_id", "registration_number", "vehicle_type"):
                if not attrs.get(required):
                    raise serializers.ValidationError({required: "This field is required."})
        vtype = attrs.get("vehicle_type")
        if vtype and vtype not in Vehicle.VehicleType.values:
            raise serializers.ValidationError({"vehicle_type": "Invalid vehicle type."})
        return attrs


class VehicleAssignSerializer(serializers.Serializer):
    assignment_type = serializers.ChoiceField(choices=VehicleAssignment.AssignmentType.choices)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    worker_id = serializers.IntegerField(required=False, allow_null=True)
    driver_id = serializers.IntegerField(required=False, allow_null=True)
    start_datetime = serializers.DateTimeField()
    end_datetime = serializers.DateTimeField(required=False, allow_null=True)
    purpose = serializers.CharField(required=False, allow_blank=True, default="")
    remarks = serializers.CharField(required=False, allow_blank=True, default="")


class VehicleUnassignSerializer(serializers.Serializer):
    assignment_id = serializers.IntegerField(required=False, allow_null=True)
    end_datetime = serializers.DateTimeField(required=False)


class VehicleHistorySerializer(serializers.ModelSerializer):
    project_number = serializers.CharField(
        source="project.project_number", read_only=True, default=None
    )
    worker_name = serializers.CharField(source="worker.full_name", read_only=True, default=None)
    driver_name = serializers.CharField(source="driver.full_name", read_only=True, default=None)
    duration_days = serializers.SerializerMethodField()

    class Meta:
        model = VehicleAssignment
        fields = (
            "id",
            "assignment_type",
            "project_number",
            "worker_name",
            "driver_name",
            "purpose",
            "start_datetime",
            "end_datetime",
            "duration_days",
            "remarks",
        )

    def get_duration_days(self, obj):
        from django.utils import timezone

        end = obj.end_datetime or timezone.now()
        delta = end - obj.start_datetime
        return round(delta.total_seconds() / 86400, 1)


class VehicleMediaSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = VehicleMedia
        fields = ("id", "file_url", "created_at")

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class VehicleMediaUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleMedia
        fields = ("file",)

    def validate_file(self, value):
        validate_image_file(value)
        return value


class VehicleBookingReadSerializer(serializers.ModelSerializer):
    project_number = serializers.CharField(
        source="project.project_number", read_only=True, default=None
    )
    worker_name = serializers.CharField(source="worker.full_name", read_only=True, default=None)
    driver_name = serializers.CharField(source="driver.full_name", read_only=True, default=None)
    booked_by_name = serializers.CharField(
        source="booked_by.mobile_number", read_only=True, default=None
    )

    class Meta:
        model = VehicleBooking
        fields = (
            "id",
            "vehicle",
            "booked_by",
            "booked_by_name",
            "driver",
            "driver_name",
            "project",
            "project_number",
            "worker",
            "worker_name",
            "booking_type",
            "start_datetime",
            "end_datetime",
            "status",
            "purpose",
            "notes",
            "created_at",
            "updated_at",
        )


class VehicleBookingWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleBooking
        fields = (
            "driver",
            "project",
            "worker",
            "booking_type",
            "start_datetime",
            "end_datetime",
            "status",
            "purpose",
            "notes",
        )
        extra_kwargs = {
            "status": {"required": False},
        }

    def validate(self, attrs):
        start = attrs.get("start_datetime")
        end = attrs.get("end_datetime")
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_datetime": "end_datetime must be after start_datetime."}
            )
        if (
            start
            and (self.instance is None or "start_datetime" in attrs)
            and start <= timezone.now()
        ):
            raise serializers.ValidationError(
                {"start_datetime": "start_datetime must be in the future."}
            )
        return attrs
