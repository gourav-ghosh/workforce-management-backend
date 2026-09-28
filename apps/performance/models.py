"""Employee Performance model.

Captures per-period evaluations judged by an admin against five named
parameters. The record is admin-evaluated and may be made visible to the
worker via ``is_visible_to_worker``. Workers never write to these rows.
"""

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.workers.models import WorkerProfile


class PerformanceRecord(TimeStampedModel):
    """One evaluation cycle for one worker.

    Scores use a 1-5 scale (1 = poor, 5 = excellent). Free-text ``notes`` give
    context for the overall assessment. ``is_visible_to_worker`` is the future
    on/off switch for worker-facing visibility.
    """

    worker = models.ForeignKey(
        WorkerProfile,
        on_delete=models.CASCADE,
        related_name="performance_records",
    )
    evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="performance_evaluations",
    )

    # Evaluation period (inclusive). Both default to the day of creation.
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)

    # Five named parameters. Stored as integers in [1, 5]; nullable so an
    # evaluator can leave a criterion blank when not applicable.
    attendance_time = models.PositiveSmallIntegerField(null=True, blank=True)
    ppe_replacement_duration = models.PositiveSmallIntegerField(null=True, blank=True)
    job_training_attendance = models.PositiveSmallIntegerField(null=True, blank=True)
    job_time = models.PositiveSmallIntegerField(null=True, blank=True)
    advance_loan_repayment = models.PositiveSmallIntegerField(null=True, blank=True)

    # Overall free-text assessment (always required to keep audit trail
    # meaningful).
    notes = models.TextField(blank=True)

    is_visible_to_worker = models.BooleanField(
        default=False,
        help_text=(
            "When true, the worker can read this evaluation via "
            "GET /api/v1/me/performance/. Admin-controlled; not flipped by "
            "workers."
        ),
    )

    class Meta:
        ordering = ["-period_end", "-id"]
        indexes = [
            models.Index(fields=["worker", "period_end"]),
            models.Index(fields=["evaluator", "period_end"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="perf_score_range",
                condition=(
                    models.Q(attendance_time__gte=1)
                    & models.Q(attendance_time__lte=5)
                    & models.Q(ppe_replacement_duration__gte=1)
                    & models.Q(ppe_replacement_duration__lte=5)
                    & models.Q(job_training_attendance__gte=1)
                    & models.Q(job_training_attendance__lte=5)
                    & models.Q(job_time__gte=1)
                    & models.Q(job_time__lte=5)
                    & models.Q(advance_loan_repayment__gte=1)
                    & models.Q(advance_loan_repayment__lte=5)
                ),
            ),
            models.CheckConstraint(
                name="perf_period_order",
                condition=models.Q(period_end__gte=models.F("period_start")),
            ),
        ]

    def __str__(self):
        return f"Performance #{self.pk} - {self.worker.employee_id}"

    @property
    def overall_score(self):
        """Mean of the five parameters, ignoring blanks. 0 if none are set."""
        values = [
            self.attendance_time,
            self.ppe_replacement_duration,
            self.job_training_attendance,
            self.job_time,
            self.advance_loan_repayment,
        ]
        filled = [v for v in values if v is not None]
        if not filled:
            return 0
        return round(sum(filled) / len(filled), 2)
