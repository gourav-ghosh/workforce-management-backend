"""Project serializers."""

from rest_framework import serializers

from apps.common.validators import validate_document_file
from apps.projects.models import Project, ProjectWorker
from apps.workers.models import WorkerProfile


class AssignedWorkerSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerProfile
        fields = (
            "id",
            "employee_id",
            "full_name",
            "designation",
        )


class ProjectWorkerSerializer(serializers.ModelSerializer):
    worker = AssignedWorkerSerializer(read_only=True)

    class Meta:
        model = ProjectWorker
        fields = ("id", "worker", "assigned_at", "unassigned_at", "is_active")


class ProjectListSerializer(serializers.ModelSerializer):
    active_workers_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            "id",
            "project_number",
            "project_name",
            "client_name",
            "location",
            "status",
            "measurement_sheet_status",
            "start_date",
            "expected_completion_date",
            "active_workers_count",
        )

    def get_active_workers_count(self, obj):
        if hasattr(obj, "active_workers_count"):
            return obj.active_workers_count
        from apps.projects.models import ProjectWorker

        return ProjectWorker.objects.filter(project=obj, is_active=True).count()


class ProjectDetailSerializer(ProjectListSerializer):
    assigned_workers = serializers.SerializerMethodField()
    project_plan_url = serializers.SerializerMethodField()
    tools_assigned_count = serializers.SerializerMethodField()
    ppe_assigned_count = serializers.SerializerMethodField()

    class Meta(ProjectListSerializer.Meta):
        fields = ProjectListSerializer.Meta.fields + (
            "description",
            "permit_no",
            "total_manpower",
            "job",
            "notes",
            "project_plan_url",
            "assigned_workers",
            "tools_assigned_count",
            "ppe_assigned_count",
            "created_at",
            "updated_at",
        )

    def get_assigned_workers(self, obj):
        assignments = obj.worker_assignments.filter(is_active=True).select_related(
            "worker", "worker__user"
        )
        return [
            {
                "assignment_id": a.id,
                **AssignedWorkerSerializer(a.worker).data,
                "assigned_at": a.assigned_at,
            }
            for a in assignments
        ]

    def get_project_plan_url(self, obj):
        request = self.context.get("request")
        if obj.project_plan and request:
            return request.build_absolute_uri(obj.project_plan.url)
        return None

    def get_tools_assigned_count(self, obj):
        from apps.tools.models import ToolAssignment

        return ToolAssignment.objects.filter(project=obj, status="ACTIVE").count()

    def get_ppe_assigned_count(self, obj):
        return 0  # PPE assignments are not project-scoped in Version 1


class ProjectWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = (
            "id",
            "project_number",
            "project_name",
            "client_name",
            "location",
            "description",
            "start_date",
            "expected_completion_date",
            "permit_no",
            "total_manpower",
            "job",
            "measurement_sheet_status",
            "status",
            "project_plan",
            "notes",
        )
        extra_kwargs = {
            "project_number": {"required": False},
            "project_name": {"required": False},
            "project_plan": {"required": False, "allow_null": True},
        }

    def validate_project_plan(self, value):
        if value:
            validate_document_file(value)
        return value

    def validate(self, attrs):
        creating = self.instance is None
        if creating:
            for required in ("project_number", "project_name"):
                if not attrs.get(required):
                    raise serializers.ValidationError({required: "This field is required."})
        start = attrs.get("start_date", self.instance.start_date if self.instance else None)
        end = attrs.get(
            "expected_completion_date",
            self.instance.expected_completion_date if self.instance else None,
        )
        if start and end and end < start:
            raise serializers.ValidationError(
                {"expected_completion_date": "Must be after the start date."}
            )
        return attrs


class ProjectWorkerAssignSerializer(serializers.Serializer):
    worker_id = serializers.IntegerField()

    def validate_worker_id(self, value):
        if not WorkerProfile.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Worker does not exist.")
        return value
