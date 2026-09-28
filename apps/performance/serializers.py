"""Employee Performance serializers."""

from rest_framework import serializers

from apps.performance.models import PerformanceRecord
from apps.workers.models import WorkerProfile


class _WorkerBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerProfile
        fields = ("id", "employee_id", "full_name", "designation")


class PerformanceRecordSerializer(serializers.ModelSerializer):
    worker_detail = _WorkerBriefSerializer(source="worker", read_only=True)
    evaluator_name = serializers.SerializerMethodField()
    overall_score = serializers.FloatField(read_only=True)

    class Meta:
        model = PerformanceRecord
        fields = (
            "id",
            "worker",
            "worker_detail",
            "evaluator",
            "evaluator_name",
            "period_start",
            "period_end",
            "attendance_time",
            "ppe_replacement_duration",
            "job_training_attendance",
            "job_time",
            "advance_loan_repayment",
            "notes",
            "is_visible_to_worker",
            "overall_score",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("evaluator", "evaluator_name", "overall_score")

    def get_evaluator_name(self, obj):
        user = obj.evaluator
        if not user:
            return None
        full = f"{user.first_name} {user.last_name}".strip()
        return full or user.mobile_number


class PerformanceRecordWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceRecord
        fields = (
            "period_start",
            "period_end",
            "attendance_time",
            "ppe_replacement_duration",
            "job_training_attendance",
            "job_time",
            "advance_loan_repayment",
            "notes",
            "is_visible_to_worker",
        )
        extra_kwargs = {
            "period_start": {"required": True},
            "period_end": {"required": True},
        }

    def validate(self, attrs):
        period_start = attrs.get("period_start")
        period_end = attrs.get("period_end")
        if period_start and period_end and period_end < period_start:
            raise serializers.ValidationError(
                {"period_end": "period_end must be on or after period_start."}
            )

        score_fields = [
            "attendance_time",
            "ppe_replacement_duration",
            "job_training_attendance",
            "job_time",
            "advance_loan_repayment",
        ]
        for field in score_fields:
            value = attrs.get(field)
            if value is None:
                continue
            if not 1 <= value <= 5:
                raise serializers.ValidationError(
                    {field: "Score must be between 1 and 5."}
                )
        return attrs
