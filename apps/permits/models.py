"""Daily TBM (Tool Box Meeting) and work-permit records.

A supervisor raises a single permit for the workers on one project for one
day; a multi-worker permit lists each of them. Per-worker uniqueness on
(project, date) is enforced in the service layer. The TBM sheet and the work
permit sheet are optional attachments, but the permit number is required
because a permit without one is not a permit.
"""

import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.common.validators import _ALLOWED_DOCUMENT_EXTENSIONS


def _permit_upload_path(prefix, filename):
    # splitext keeps the leading dot, which is what the allow-list entries
    # look like. Comparing a dotless extension here silently forced every
    # upload - including photos - to be stored as ".pdf".
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_DOCUMENT_EXTENSIONS:
        ext = ".pdf"
    return f"{prefix}/{uuid.uuid4().hex}{ext}"


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
    """A project crew's TBM acknowledgement and work permit for one day."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="work_permits",
    )
    # A permit can name several workers at once (a supervisor raises one TBM
    # for the whole crew, not one per person). Per-worker uniqueness on
    # (project, date) is enforced in the service layer because a worker's
    # membership in a project-crew permit lives on the M2M join table.
    workers = models.ManyToManyField(
        "workers.WorkerProfile",
        related_name="permits_raised_for",
        blank=True,
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
        ordering = ["-date", "project_id", "id"]
        verbose_name_plural = "work permits"
        indexes = [
            models.Index(fields=["project", "date"]),
        ]

    def __str__(self):
        return f"{self.project_id} {self.date} #{self.pk}"

    @property
    def worker_count(self):
        return self.workers.count()

    @property
    def has_tbm_sheet(self):
        return bool(self.tbm_sheet)

    @property
    def has_work_permit_sheet(self):
        return bool(self.work_permit_sheet)

    @property
    def attachment_count(self):
        return int(bool(self.tbm_sheet)) + int(bool(self.work_permit_sheet))
