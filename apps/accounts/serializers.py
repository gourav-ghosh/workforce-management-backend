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
    """Returns access/refresh tokens plus basic user information."""

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
        fields = ("id", "username", "email", "role", "worker_profile")


class MeSerializer(UserBriefSerializer):
    pass


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text="Username or email address of the account.")


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
