"""Worker field attendance.

One record per (worker, project, date). A supervisor marks attendance for the
workers on the projects they are assigned to; an admin can mark anyone's.

The late flag and the worked-hours figure are derived, never stored, so that
changing ``ATTENDANCE_START_TIME`` immediately re-classifies existing records
instead of leaving stale booleans in the database.
"""

from datetime import datetime, timedelta
from datetime import time as dt_time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


def attendance_timezone():
    """Return the timezone the shift-start threshold is expressed in."""
    return ZoneInfo(settings.ATTENDANCE_TIMEZONE)


def shift_start_threshold():
    """Return the configured shift start as a (hour, minute) tuple."""
    raw = str(settings.ATTENDANCE_START_TIME).strip()
    parts = raw.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError) as exc:
        raise ValueError(f"ATTENDANCE_START_TIME must look like 'HH:MM', got {raw!r}") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"ATTENDANCE_START_TIME out of range: {raw!r}")
    return hour, minute


def today_in_attendance_tz():
    """Today's date in the attendance timezone (not the server's UTC date)."""
    return datetime.now(tz=attendance_timezone()).date()


def max_backdate_days():
    return int(getattr(settings, "ATTENDANCE_MAX_BACKDATE_DAYS", 2))


def lunch_break_minutes():
    """Daily lunch break deducted from worked hours, in minutes."""
    return int(getattr(settings, "ATTENDANCE_LUNCH_BREAK_MINUTES", 60))


def earliest_allowed_date():
    return today_in_attendance_tz() - timedelta(days=max_backdate_days())


class AttendanceRecord(TimeStampedModel):
    """A single punch-in / punch-out pair for one worker on one project."""

    worker = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.PROTECT,
        related_name="attendance_records",
    )
    # Optional: an admin may log attendance for any employee even when they
    # are not assigned to a project. Supervisors always set a project.
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attendance_records",
    )
    date = models.DateField(db_index=True)
    punch_in = models.DateTimeField()
    punch_out = models.DateTimeField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attendance_records_marked",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "worker_id"]
        verbose_name_plural = "attendance records"
        constraints = [
            # Split into two conditional constraints because SQL treats NULLs
            # as distinct: without the second one, an admin could log the same
            # project-less record for a worker twice on the same day.
            models.UniqueConstraint(
                fields=["worker", "project", "date"],
                condition=models.Q(project__isnull=False),
                name="uniq_attendance_worker_project_date",
            ),
            models.UniqueConstraint(
                fields=["worker", "date"],
                condition=models.Q(project__isnull=True),
                name="uniq_attendance_worker_date_no_project",
            ),
            models.CheckConstraint(
                condition=models.Q(punch_out__isnull=True)
                | models.Q(punch_out__gt=models.F("punch_in")),
                name="chk_attendance_punch_out_after_in",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "date"]),
            models.Index(fields=["worker", "date"]),
        ]

    def __str__(self):
        return f"{self.worker_id}@{self.project_id} {self.date}"

    @property
    def shift_start(self):
        """The threshold instant for this record's date, timezone-aware."""
        hour, minute = shift_start_threshold()
        return datetime.combine(self.date, dt_time(hour, minute), tzinfo=attendance_timezone())

    @property
    def is_late(self):
        """True when the punch-in is after the configured shift start."""
        return self.punch_in > self.shift_start

    @property
    def late_by_minutes(self):
        """Whole minutes after the shift start; 0 when not late."""
        if not self.is_late:
            return 0
        return int((self.punch_in - self.shift_start).total_seconds() // 60)

    @property
    def work_hours(self):
        """Billable hours: the worked span minus the daily lunch break.

        The raw span between punch-in and punch-out runs long for a whole
        site day — 08:00 to 17:00 is nine hours on site but eight hours
        worked. The break is configurable via ATTENDANCE_LUNCH_BREAK_MINUTES
        and is never allowed to push the result below zero.
        """
        if not self.punch_out:
            return None
        worked = (self.punch_out - self.punch_in).total_seconds() / 3600
        lunch_hours = lunch_break_minutes() / 60
        return round(max(0.0, worked - lunch_hours), 2)

    @property
    def is_open(self):
        return self.punch_out is None
