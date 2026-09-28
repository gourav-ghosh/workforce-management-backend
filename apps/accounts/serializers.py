"""Account serializers: login, token refresh payloads, me, password flows."""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.workers.models import WorkerProfile

User = get_user_model()


class WorkerProfileBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerProfile
        fields = (
            "id",
            "employee_id",
            "full_name",
            "phone_number",
            "designation",
            "employment_status",
            "profile_photo",
        )


class LoginTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Returns access/refresh tokens plus basic user information.

    Login is performed with ``mobile_number`` + ``password`` instead of the
    Django ``username`` field.
    """

    username_field = "mobile_number"

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserBriefSerializer(self.user).data
        return data


class UserBriefSerializer(serializers.ModelSerializer):
    worker_profile = WorkerProfileBriefSerializer(read_only=True)

    class Meta:
        model = User
        fields = ("id", "mobile_number", "email", "role", "worker_profile")


class MeSerializer(UserBriefSerializer):
    pass


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(
        help_text="Mobile number or email address of the account."
    )


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        validate_password(value)
        return value


class AdminPasswordResetSerializer(serializers.Serializer):
    """Allows an admin to set a new password for a user."""

    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class WorkerSelfPasswordResetSerializer(serializers.Serializer):
    """Worker resets their own password using the current default password.

    This is the flow a worker uses when they first log in with the default
    password set by the admin, or when they forget the password and the admin
    has re-issued a default one.
    """

    mobile_number = serializers.CharField(help_text="Worker's mobile number (login id).")
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_mobile_number(self, value):
        if not User.objects.filter(mobile_number=value, is_active=True).exists():
            raise serializers.ValidationError("No active account for this mobile number.")
        return value

    def validate_current_password(self, value):
        user = User.objects.get(mobile_number=self.validated_data["mobile_number"])
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        validate_password(value)
        return value


# ---------------------------------------------------------------------------
# "My assignment" serializers used by the worker experience (/api/v1/me/*).
# The nested serializers operate on the related object itself.
# ---------------------------------------------------------------------------


class MyProjectBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    project_number = serializers.CharField()
    project_name = serializers.CharField()
    client_name = serializers.CharField()
    location = serializers.CharField()
    status = serializers.CharField()
    start_date = serializers.DateField()
    expected_completion_date = serializers.DateField(allow_null=True)
    description = serializers.CharField()


class MyProjectAssignmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    project = MyProjectBriefSerializer()
    assigned_at = serializers.DateTimeField()


class MyToolBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    tool_id = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()
    condition = serializers.CharField()


class MyToolAssignmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    tool = MyToolBriefSerializer()
    issue_date = serializers.DateField()
    expected_return_date = serializers.DateField(allow_null=True)
    issue_condition = serializers.CharField()
    remarks = serializers.CharField()


class _ToolDamageMediaItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    file_url = serializers.SerializerMethodField()
    media_type = serializers.CharField()
    created_at = serializers.DateTimeField()

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not obj.file:
            return None
        try:
            url = obj.file.url
        except ValueError:
            return None
        if not url:
            return None
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class _ToolDamageForWorkerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    damage_date = serializers.DateField()
    description = serializers.CharField(source="damage_description")
    condition = serializers.CharField(source="damage_condition")
    repair_status = serializers.CharField()
    remarks = serializers.CharField(allow_blank=True)
    media = _ToolDamageMediaItemSerializer(many=True)


class _ToolAssignmentMediaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    file_url = serializers.SerializerMethodField()
    media_type = serializers.CharField()
    created_at = serializers.DateTimeField()

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not obj.file:
            return None
        try:
            url = obj.file.url
        except ValueError:
            return None
        if not url:
            return None
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class MyToolHistoryAssignmentSerializer(serializers.Serializer):
    """Worker-facing tool assignment with damage and media for history view."""

    id = serializers.IntegerField()
    worker = serializers.IntegerField(source="worker_id")
    tool = MyToolBriefSerializer()
    issue_date = serializers.DateField()
    expected_return_date = serializers.DateField(allow_null=True)
    return_date = serializers.DateField(allow_null=True)
    issue_condition = serializers.CharField()
    return_condition = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    remarks = serializers.CharField(allow_blank=True)
    damages = _ToolDamageForWorkerSerializer(many=True)
    media = _ToolAssignmentMediaSerializer(many=True)


class MyToolDamageReportInputSerializer(serializers.Serializer):
    """Worker reports damage for one of their own assignments."""

    damage_description = serializers.CharField()
    damage_condition = serializers.ChoiceField(
        choices=["EXCELLENT", "GOOD", "FAIR", "POOR", "DAMAGED"]
    )
    remarks = serializers.CharField(required=False, allow_blank=True, default="")
    photos = serializers.ListField(
        child=serializers.ImageField(), required=False, write_only=True
    )


class MyPPEBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    ppe_id = serializers.CharField()
    ppe_type = serializers.CharField()
    name = serializers.CharField()
    size = serializers.CharField()


class MyPPEAssignmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    ppe = MyPPEBriefSerializer()
    issue_date = serializers.DateField()
    expected_return_date = serializers.DateField(allow_null=True)
    issue_condition = serializers.CharField()
    remarks = serializers.CharField()


class MyVehicleBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    vehicle_id = serializers.CharField()
    registration_number = serializers.CharField()
    vehicle_type = serializers.CharField()
    make_model = serializers.CharField()


class MyVehicleAssignmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    vehicle = MyVehicleBriefSerializer()
    assignment_type = serializers.CharField()
    role = serializers.SerializerMethodField()
    start_datetime = serializers.DateTimeField()
    end_datetime = serializers.DateTimeField(allow_null=True)
    purpose = serializers.CharField()

    def get_role(self, obj):
        worker_profile_id = self.context.get("worker_profile_id")
        if worker_profile_id and obj.driver_id == worker_profile_id:
            return "driver"
        return "worker"

    def validate_new_password(self, value):
        validate_password(value)
        return value
