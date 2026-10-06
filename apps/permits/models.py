"""Daily TBM (Tool Box Meeting) and work-permit records.

One record per worker per project per day. A supervisor raises them for the
workers on the projects they are assigned to; an admin can raise them for
anyone. The TBM sheet and the work-permit sheet are optional attachments, but
the permit number is required because a permit without one is not a permit.
"""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.common.validators import _ALLOWED_DOCUMENT_EXTENSIONS


def _permit_upload_path(prefix, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_DOCUMENT_EXTENSIONS:
        ext = ".pdf"
    return f"{prefix}/{uuid.uuid4().hex}.{ext}"


def tbm_sheet_upload_to(instance, filename):
    return _permit_upload_path("permits/tbm_sheets", filename)


def work_permit_sheet_upload_to(instance, filename):
    return _permit_upload_path("permits/work_permit_sheets", filename)


def permits_timezone():
    return ZoneInfo(settings.ATTENDANCE_TIMEZONE)


def today_in_permits_tz():
    """Today's date in the business timezone, matching how permits are dated."""
    return datetime.now(tz=permits_timezone()).date()


def max_backdate_days():
    return int(getattr(settings, "PERMIT_MAX_BACKDATE_DAYS", 2))


def earliest_allowed_date():
    return today_in_permits_tz() - timedelta(days=max_backdate_days())


class WorkPermit(TimeStampedModel):
    """A worker's TBM acknowledgement and work permit for one project, one day."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="work_permits",
    )
    worker = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.PROTECT,
        related_name="work_permits",
    )
    date = models.DateField(db_index=True)
    work_permit_number = models.CharField(max_length=100)

    # Both sheets are optional: a supervisor may not always have the scan to
    # hand, and blocking the record would mean losing the permit number too.
    tbm_sheet = models.FileField(
        upload_to=tbm_sheet_upload_to,
        null=True,
        blank=True,
    )
    work_permit_sheet = models.FileField(
        upload_to=work_permit_sheet_upload_to,
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="work_permits_raised",
    )

    class Meta:
        ordering = ["-date", "project_id", "worker_id"]
        verbose_name_plural = "work permits"
        constraints = [
            # One permit per worker per project per day.
            models.UniqueConstraint(
                fields=["project", "worker", "date"],
                name="uniq_work_permit_project_worker_date",
            )
        ]
        indexes = [
            models.Index(fields=["project", "date"]),
            models.Index(fields=["worker", "date"]),
        ]

    def __str__(self):
        return f"{self.project_id}/{self.worker_id} {self.date}"

    @property
    def has_tbm_sheet(self):
        return bool(self.tbm_sheet)

    @property
    def has_work_permit_sheet(self):
        return bool(self.work_permit_sheet)

    @property
    def attachment_count(self):
        return int(bool(self.tbm_sheet)) + int(bool(self.work_permit_sheet))
