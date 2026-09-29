"""Worker serializers."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.common.validators import validate_image_file
from apps.workers.models import WorkerProfile

User = get_user_model()


class WorkerListSerializer(serializers.ModelSerializer):
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = WorkerProfile
        fields = (
            "id",
            "employee_id",
            "full_name",
            "designation",
            "phone_number",
            "employment_status",
            "is_supervisor",
            "profile_photo_url",
        )

    def get_profile_photo_url(self, obj):
        request = self.context.get("request")
        if obj.profile_photo and request:
            return request.build_absolute_uri(obj.profile_photo.url)
        return None


class CurrentProjectSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="project.id")
    project_number = serializers.CharField(source="project.project_number")
    project_name = serializers.CharField(source="project.project_name")
    status = serializers.CharField(source="project.status")


class AssignedToolBriefSerializer(serializers.Serializer):
    assignment_id = serializers.IntegerField(source="id")
    tool_id_code = serializers.CharField(source="tool.tool_id")
    tool_name = serializers.CharField(source="tool.name")
    issue_date = serializers.DateField()
    expected_return_date = serializers.DateField(allow_null=True)


class AssignedPPEBriefSerializer(serializers.Serializer):
    assignment_id = serializers.IntegerField(source="id")
    ppe_id_code = serializers.CharField(source="ppe.ppe_id")
    ppe_name = serializers.CharField(source="ppe.name")
    ppe_type = serializers.CharField(source="ppe.ppe_type")
    issue_date = serializers.DateField()
    expected_return_date = serializers.DateField(allow_null=True)


class VehicleAssignmentBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    vehicle_id_code = serializers.CharField(source="vehicle.vehicle_id")
    registration_number = serializers.CharField(source="vehicle.registration_number")
    assignment_type = serializers.CharField()
    start_datetime = serializers.DateTimeField()
    end_datetime = serializers.DateTimeField(allow_null=True)
    role = serializers.CharField(help_text="'driver' or 'worker'")


class WorkerDetailSerializer(WorkerListSerializer):
    current_projects = serializers.SerializerMethodField()
    assigned_tools = serializers.SerializerMethodField()
    assigned_ppe = serializers.SerializerMethodField()
    vehicle_assignments = serializers.SerializerMethodField()

    class Meta(WorkerListSerializer.Meta):
        fields = WorkerListSerializer.Meta.fields + (
            "emergency_contact_name",
            "emergency_contact_phone",
            "current_projects",
            "assigned_tools",
            "assigned_ppe",
            "vehicle_assignments",
            "created_at",
            "updated_at",
        )

    def get_current_projects(self, obj):
        assignments = obj.project_assignments.filter(is_active=True).select_related("project")
        return CurrentProjectSerializer(assignments, many=True).data

    def get_assigned_tools(self, obj):
        assignments = obj.tool_assignments.select_related("tool").filter(status="ACTIVE")
        return AssignedToolBriefSerializer(assignments, many=True).data

    def get_assigned_ppe(self, obj):
        assignments = obj.ppe_assignments.select_related("ppe").filter(status="ACTIVE")
        return AssignedPPEBriefSerializer(assignments, many=True).data

    def get_vehicle_assignments(self, obj):
        from apps.transportation.services import open_vehicle_assignments_for_worker

        data = []
        for assignment in open_vehicle_assignments_for_worker(obj):
            role = "driver" if assignment.driver_id == obj.id else "worker"
            item = VehicleAssignmentBriefSerializer(assignment).data
            item["role"] = role
            data.append(item)
        return data


class WorkerWriteSerializer(serializers.ModelSerializer):
    mobile_number = serializers.CharField(
        write_only=True,
        required=False,
        help_text="Login mobile number. Required when creating a worker.",
    )
    password = serializers.CharField(
        write_only=True,
        required=False,
        help_text=(
            "Initial login password. Required when creating a worker. "
            "The admin must set this value directly — there is no env-level default."
        ),
    )
    email = serializers.EmailField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Optional account email (used for password reset).",
    )

    class Meta:
        model = WorkerProfile
        fields = (
            "employee_id",
            "full_name",
            "phone_number",
            "designation",
            "employment_status",
            "is_supervisor",
            "emergency_contact_name",
            "emergency_contact_phone",
            "profile_photo",
            "mobile_number",
            "password",
            "email",
        )
        extra_kwargs = {
            "profile_photo": {"required": False, "allow_null": True},
        }

    def validate_profile_photo(self, value):
        if value:
            validate_image_file(value)
        return value

    def validate_employment_status(self, value):
        if value not in WorkerProfile.EmploymentStatus.values:
            raise serializers.ValidationError("Invalid employment status.")
        return value

    def _validate_account_fields(self, attrs, creating):
        mobile_number = attrs.get("mobile_number")
        password = attrs.get("password")
        if creating:
            if not mobile_number:
                raise serializers.ValidationError(
                    {"mobile_number": "Mobile number is required when creating a worker."}
                )
            if not password:
                raise serializers.ValidationError(
                    {
                        "password": (
                            "A password is required. Admins must set the initial password "
                            "for the new worker account."
                        )
                    }
                )
            if User.objects.filter(mobile_number=mobile_number).exists():
                raise serializers.ValidationError(
                    {"mobile_number": "A user with this mobile number already exists."}
                )
            from django.contrib.auth.password_validation import validate_password

            try:
                validate_password(password)
            except Exception as exc:
                raise serializers.ValidationError({"password": list(exc.messages)})
        else:
            if mobile_number or password:
                raise serializers.ValidationError(
                    {
                        "mobile_number": (
                            "Account credentials cannot be changed here. "
                            "Use the reset-password endpoint."
                        )
                    }
                )
        return attrs

    def validate(self, attrs):
        creating = self.instance is None
        self._validate_account_fields(attrs, creating)
        return attrs


class AdminPasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True)


class WorkerSelfPasswordResetSerializer(serializers.Serializer):
    """Worker resets their own password using the current default password."""

    mobile_number = serializers.CharField(help_text="Worker's mobile number (login id).")
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_mobile_number(self, value):
        if not User.objects.filter(mobile_number=value, is_active=True).exists():
            raise serializers.ValidationError("No active account for this mobile number.")
        return value

    def validate(self, attrs):
        user = User.objects.get(mobile_number=attrs["mobile_number"])
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError(
                {"current_password": "Current password is incorrect."}
            )
        from django.contrib.auth.password_validation import validate_password

        try:
            validate_password(attrs["new_password"], user=user)
        except Exception as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs
