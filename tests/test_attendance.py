"""Attendance module tests.

Covers the late threshold (including the timezone conversion that the whole
feature hinges on), worked hours, and the admin/supervisor scoping rules.
"""

from datetime import date, datetime, timedelta
from datetime import time as dt_time
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, today_in_attendance_tz
from apps.projects.models import Project, ProjectWorker
from apps.workers.models import WorkerProfile

IST = ZoneInfo("Asia/Kolkata")
URL = "/api/v1/attendance/"

# Attendance is a daily log, so the API tests anchor on "today" rather than a
# fixed date. The late/derived tests build records directly on the model.
today = today_in_attendance_tz()


def ist(year, month, day, hour, minute=0):
    """Build an aware datetime in the attendance timezone."""
    return datetime(year, month, day, hour, minute, tzinfo=IST)


def punch_today(hour, minute=0):
    """An aware datetime today at the given wall-clock time (IST)."""
    return punch_on(today, hour, minute)


def punch_on(day, hour, minute=0):
    """An aware datetime on [day] at the given wall-clock time (IST)."""
    return datetime.combine(day, dt_time(hour, minute), tzinfo=IST)


class AttendanceTestBase(TestCase):
    def setUp(self):
        # The service resolves "today" per request in the attendance timezone,
        # so the module-level anchor is refreshed here. Without this a run that
        # straddles IST midnight would see the window shifted by a day and fail
        # for reasons unrelated to the code under test.
        global today
        today = today_in_attendance_tz()
        self.admin = User.objects.create_user(
            mobile_number="+91 90000 10000", password="Admin@12345", role=User.Role.ADMIN
        )
        self.sup_user = User.objects.create_user(
            mobile_number="+91 90000 20000", password="Work@12345", role=User.Role.WORKER
        )
        self.supervisor = WorkerProfile.objects.create(
            user=self.sup_user,
            employee_id="SUP1",
            full_name="Site Supervisor",
            phone_number="+91 90000 20000",
            is_supervisor=True,
        )
        self.other_sup_user = User.objects.create_user(
            mobile_number="+91 90000 20001", password="Work@12345", role=User.Role.WORKER
        )
        self.other_supervisor = WorkerProfile.objects.create(
            user=self.other_sup_user,
            employee_id="SUP2",
            full_name="Other Supervisor",
            phone_number="+91 90000 20001",
            is_supervisor=True,
        )
        self.worker_user = User.objects.create_user(
            mobile_number="+91 90000 30000", password="Work@12345", role=User.Role.WORKER
        )
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            employee_id="WRK1",
            full_name="Ramesh Kumar",
            phone_number="+91 90000 30000",
        )
        self.plain_user = User.objects.create_user(
            mobile_number="+91 90000 40000", password="Work@12345", role=User.Role.WORKER
        )
        self.plain = WorkerProfile.objects.create(
            user=self.plain_user,
            employee_id="WRK2",
            full_name="Plain Worker",
            phone_number="+91 90000 40000",
        )

        self.project = Project.objects.create(project_number="PRJ-1", project_name="Site A")
        self.other_project = Project.objects.create(project_number="PRJ-2", project_name="Site B")
        ProjectWorker.objects.create(project=self.project, worker=self.supervisor)
        ProjectWorker.objects.create(project=self.project, worker=self.worker)
        ProjectWorker.objects.create(project=self.other_project, worker=self.other_supervisor)
        ProjectWorker.objects.create(project=self.other_project, worker=self.plain)

        self.admin_client = APIClient()
        self.admin_client.force_authenticate(self.admin)
        self.sup_client = APIClient()
        self.sup_client.force_authenticate(self.sup_user)
        self.worker_client = APIClient()
        self.worker_client.force_authenticate(self.worker_user)

    def _make_worker(self, employee_id, mobile):
        user = User.objects.create_user(
            mobile_number=mobile, password="Work@12345", role=User.Role.WORKER
        )
        return WorkerProfile.objects.create(
            user=user,
            employee_id=employee_id,
            full_name=employee_id,
            phone_number=mobile,
        )

    def payload(self, **overrides):
        """A valid create payload.

        The punch times follow the working date unless overridden: the API
        requires `punch_in`/`punch_out` to fall on the same calendar day as
        `date`, so a backdated record needs backdated timestamps too.
        """
        raw = overrides.get("date")
        if isinstance(raw, date):
            day = raw
        elif raw:
            day = date.fromisoformat(raw)
        else:
            day = today
        data = {
            "worker": self.worker.pk,
            "project": self.project.pk,
            "date": day.isoformat(),
            "punch_in": punch_on(day, 8).isoformat(),
            "punch_out": punch_on(day, 17).isoformat(),
        }
        data.update(overrides)
        return data


@override_settings(
    ATTENDANCE_START_TIME="08:00",
    ATTENDANCE_TIMEZONE="Asia/Kolkata",
    ATTENDANCE_MAX_BACKDATE_DAYS=2,
)
class AttendanceAdminScopeTests(AttendanceTestBase):
    """An admin may log attendance for anyone, with or without a project."""

    def test_admin_can_mark_worker_with_no_project(self):
        response = self.admin_client.post(URL, self.payload(project=None), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data["project"])
        self.assertIsNone(response.data["project_detail"])

    def test_admin_can_mark_unassigned_worker_with_no_project(self):
        """The whole point: any employee, even with zero project assignments."""
        orphan = self._make_worker("WRK-ORPHAN", "9876500000")
        response = self.admin_client.post(
            URL,
            self.payload(worker=orphan.pk, project=None),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["worker"], orphan.pk)

    def test_admin_may_ignore_project_assignment_when_a_project_is_given(self):
        orphan = self._make_worker("WRK-ORPHAN2", "9876500001")
        response = self.admin_client.post(URL, self.payload(worker=orphan.pk), format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_duplicate_project_less_entry_is_rejected(self):
        self.assertEqual(
            self.admin_client.post(URL, self.payload(project=None), format="json").status_code,
            201,
        )
        response = self.admin_client.post(URL, self.payload(project=None), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "ATTENDANCE_ALREADY_RECORDED")

    def test_supervisor_must_choose_a_project(self):
        response = self.sup_client.post(URL, self.payload(project=None), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "PROJECT_REQUIRED")

    def test_admin_can_clear_the_project_with_an_explicit_null(self):
        created = self.admin_client.post(URL, self.payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        detail = f"{URL}{created.data['id']}/"
        response = self.admin_client.patch(detail, {"project": None}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["project"])

    def test_patch_without_a_project_key_keeps_the_project(self):
        created = self.admin_client.post(URL, self.payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        detail = f"{URL}{created.data['id']}/"
        response = self.admin_client.patch(detail, {"notes": "late"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["project"], self.project.pk)

    def test_supervisor_cannot_clear_the_project(self):
        created = self.sup_client.post(URL, self.payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        detail = f"{URL}{created.data['id']}/"
        response = self.sup_client.patch(detail, {"project": None}, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "PROJECT_REQUIRED")

    def test_supervisor_still_requires_project_assignment(self):
        orphan = self._make_worker("WRK-ORPHAN3", "9876500002")
        response = self.sup_client.post(URL, self.payload(worker=orphan.pk), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "WORKER_NOT_ON_PROJECT")

    def test_supervisor_does_not_see_admin_project_less_entries(self):
        self.admin_client.post(URL, self.payload(project=None), format="json")
        self.sup_client.get(URL)
        response = self.sup_client.get(URL)
        self.assertEqual(response.data["count"], 0, "project-less entries are not the supervisor's")

    def test_admin_sees_project_less_entries(self):
        self.admin_client.post(URL, self.payload(project=None), format="json")
        self.assertEqual(self.admin_client.get(URL).data["count"], 1)


@override_settings(
    ATTENDANCE_START_TIME="08:00",
    ATTENDANCE_TIMEZONE="Asia/Kolkata",
    ATTENDANCE_MAX_BACKDATE_DAYS=2,
)
class AttendanceBackdateTests(AttendanceTestBase):
    """Attendance is a daily log: today or up to 2 days back, never ahead."""

    def test_today_is_allowed(self):
        response = self.admin_client.post(URL, self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_two_days_back_is_allowed(self):
        response = self.admin_client.post(
            URL, self.payload(date=(today - timedelta(days=2)).isoformat()), format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_three_days_back_is_rejected(self):
        response = self.admin_client.post(
            URL, self.payload(date=(today - timedelta(days=3)).isoformat()), format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "ATTENDANCE_TOO_OLD")

    def test_future_date_is_rejected(self):
        response = self.admin_client.post(
            URL, self.payload(date=(today + timedelta(days=1)).isoformat()), format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "ATTENDANCE_FUTURE_DATE")

    def test_backdating_an_existing_record_is_rejected(self):
        # Created straight on the model to get a record that predates the
        # allowed window, then try to push it further out.
        old = AttendanceRecord.objects.create(
            worker=self.worker,
            project=self.project,
            date=today - timedelta(days=1),
            punch_in=punch_on(today - timedelta(days=1), 8),
            punch_out=punch_on(today - timedelta(days=1), 17),
            recorded_by=self.admin,
        )
        target = today - timedelta(days=3)
        response = self.admin_client.patch(
            f"{URL}{old.pk}/",
            {
                "date": target.isoformat(),
                "punch_in": punch_on(target, 8).isoformat(),
                "punch_out": punch_on(target, 17).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "ATTENDANCE_TOO_OLD")

    def test_date_can_be_corrected_inside_the_window(self):
        """Moving a record to another allowed day moves its punch times too."""
        record = self.admin_client.post(URL, self.payload(), format="json").data
        moved = today - timedelta(days=1)
        response = self.admin_client.patch(
            f"{URL}{record['id']}/",
            {
                "date": moved.isoformat(),
                "punch_in": punch_on(moved, 8).isoformat(),
                "punch_out": punch_on(moved, 17).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["date"], moved.isoformat())

    def test_punch_in_from_a_different_day_is_rejected(self):
        """`date` drives the late figure, so a stray timestamp corrupts it."""
        response = self.admin_client.post(
            URL,
            self.payload(
                date=(today - timedelta(days=1)).isoformat(),
                punch_in=punch_today(8).isoformat(),
                punch_out=punch_today(17).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("punch_in", response.data)


@override_settings(ATTENDANCE_START_TIME="08:00", ATTENDANCE_TIMEZONE="Asia/Kolkata")
class AttendanceLateTests(AttendanceTestBase):
    def test_punch_in_exactly_at_threshold_is_not_late(self):
        record = AttendanceRecord.objects.create(
            worker=self.worker,
            project=self.project,
            date=date(2026, 9, 19),
            punch_in=ist(2026, 9, 19, 8),
            punch_out=ist(2026, 9, 19, 17),
        )
        self.assertFalse(record.is_late)
        self.assertEqual(record.late_by_minutes, 0)

    def test_punch_in_after_threshold_is_late(self):
        record = AttendanceRecord.objects.create(
            worker=self.worker,
            project=self.project,
            date=date(2026, 9, 19),
            punch_in=ist(2026, 9, 19, 8, 30),
            punch_out=ist(2026, 9, 19, 17),
        )
        self.assertTrue(record.is_late)
        self.assertEqual(record.late_by_minutes, 30)

    def test_late_is_judged_in_configured_timezone_not_utc(self):
        """08:30 IST is 03:00 UTC. Judged against UTC it would look on time."""
        record = AttendanceRecord.objects.create(
            worker=self.worker,
            project=self.project,
            date=date(2026, 9, 19),
            punch_in=ist(2026, 9, 19, 8, 30),
            punch_out=ist(2026, 9, 19, 17),
        )
        self.assertEqual(
            record.punch_in.astimezone(dt_timezone.utc).hour,
            3,
            "stored as 03:00 UTC",
        )
        self.assertTrue(record.is_late, "08:30 IST must be late against an 08:00 IST shift")

    def test_work_hours_are_calculated(self):
        record = AttendanceRecord.objects.create(
            worker=self.worker,
            project=self.project,
            date=date(2026, 9, 19),
            punch_in=ist(2026, 9, 19, 9),
            punch_out=ist(2026, 9, 19, 17, 30),
        )
        # 8.5h on site minus the 1h lunch break = 7.5h worked.
        self.assertEqual(record.work_hours, 7.5)

    def test_work_hours_deduct_the_lunch_break(self):
        # 08:00 to 17:00 is nine hours on site but eight worked hours.
        record = AttendanceRecord.objects.create(
            worker=self.worker,
            project=self.project,
            date=date(2026, 9, 19),
            punch_in=ist(2026, 9, 19, 8),
            punch_out=ist(2026, 9, 19, 17),
        )
        self.assertEqual(record.work_hours, 8.0)
        with override_settings(ATTENDANCE_LUNCH_BREAK_MINUTES=0):
            self.assertEqual(record.work_hours, 9.0)

    def test_worked_hours_never_go_below_zero(self):
        # A half-hour shift still deducts the lunch break, but clamps to 0.
        record = AttendanceRecord.objects.create(
            worker=self.worker,
            project=self.project,
            date=date(2026, 9, 19),
            punch_in=ist(2026, 9, 19, 9),
            punch_out=ist(2026, 9, 19, 9, 30),
        )
        self.assertEqual(record.work_hours, 0.0)

    def test_open_record_has_no_work_hours(self):
        record = AttendanceRecord.objects.create(
            worker=self.worker,
            project=self.project,
            date=date(2026, 9, 19),
            punch_in=ist(2026, 9, 19, 9),
        )
        self.assertIsNone(record.work_hours)
        self.assertTrue(record.is_open)

    def test_threshold_is_configurable(self):
        record = AttendanceRecord.objects.create(
            worker=self.worker,
            project=self.project,
            date=date(2026, 9, 19),
            punch_in=ist(2026, 9, 19, 10),
            punch_out=ist(2026, 9, 19, 18),
        )
        self.assertTrue(record.is_late)
        with override_settings(ATTENDANCE_START_TIME="10:00"):
            self.assertFalse(record.is_late, "10:00 shift start makes a 10:00 punch on time")

    def test_api_reports_derived_fields(self):
        response = self.admin_client.post(
            URL, self.payload(punch_in=punch_today(9).isoformat()), format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        body = response.data
        self.assertTrue(body["is_late"])
        self.assertEqual(body["late_by_minutes"], 60)
        # 09:00 to 17:00 is 8h on site, minus the 1h lunch break = 7h.
        self.assertEqual(body["work_hours"], 7.0)
        self.assertFalse(body["is_open"])
        self.assertEqual(body["worker_detail"]["full_name"], "Ramesh Kumar")
        self.assertEqual(body["project_detail"]["project_number"], "PRJ-1")


@override_settings(ATTENDANCE_START_TIME="08:00", ATTENDANCE_TIMEZONE="Asia/Kolkata")
class AttendancePermissionTests(AttendanceTestBase):
    def test_plain_worker_cannot_mark_attendance(self):
        response = self.worker_client.post(URL, self.payload(), format="json")
        self.assertEqual(response.status_code, 403)

    def test_plain_worker_cannot_list_attendance(self):
        self.assertEqual(self.worker_client.get(URL).status_code, 403)

    def test_supervisor_can_mark_for_worker_on_their_project(self):
        response = self.sup_client.post(URL, self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_supervisor_blocked_outside_their_projects(self):
        response = self.sup_client.post(
            URL,
            self.payload(worker=self.plain.pk, project=self.other_project.pk),
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "SUPERVISOR_OUT_OF_SCOPE")

    def test_admin_can_mark_anyone(self):
        response = self.admin_client.post(
            URL,
            self.payload(worker=self.plain.pk, project=self.other_project.pk),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_admin_may_mark_a_worker_who_is_not_on_the_project(self):
        """Admins log attendance for all employees, assigned or not."""
        response = self.admin_client.post(
            URL,
            self.payload(worker=self.plain.pk, project=self.project.pk),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_supervisor_list_is_scoped_to_their_projects(self):
        self.admin_client.post(URL, self.payload(), format="json")
        self.admin_client.post(
            URL,
            self.payload(
                worker=self.plain.pk,
                project=self.other_project.pk,
                date=(today - timedelta(days=1)).isoformat(),
                punch_in=punch_today(8).isoformat(),
                punch_out=punch_today(17).isoformat(),
            ),
            format="json",
        )
        response = self.sup_client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["project"], self.project.pk)

    def test_admin_list_sees_everything(self):
        self.admin_client.post(URL, self.payload(), format="json")
        self.admin_client.post(
            URL,
            self.payload(
                worker=self.plain.pk,
                project=self.other_project.pk,
                date=(today - timedelta(days=1)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(self.admin_client.get(URL).data["count"], 2)

    def test_supervisor_cannot_see_other_projects_record(self):
        record = self.admin_client.post(
            URL,
            self.payload(worker=self.plain.pk, project=self.other_project.pk),
            format="json",
        ).data
        response = self.sup_client.get(f"{URL}{record['id']}/")
        self.assertEqual(response.status_code, 404)

    def test_only_admin_can_delete(self):
        record = self.admin_client.post(URL, self.payload(), format="json").data
        self.assertEqual(self.sup_client.delete(f"{URL}{record['id']}/").status_code, 403)
        self.assertEqual(self.admin_client.delete(f"{URL}{record['id']}/").status_code, 204)


@override_settings(ATTENDANCE_START_TIME="08:00", ATTENDANCE_TIMEZONE="Asia/Kolkata")
class AttendanceValidationTests(AttendanceTestBase):
    def test_punch_out_before_punch_in_rejected(self):
        response = self.admin_client.post(
            URL,
            self.payload(
                punch_in=ist(2026, 9, 19, 17).isoformat(),
                punch_out=ist(2026, 9, 19, 9).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("punch_out", response.data)

    def test_duplicate_worker_project_date_rejected(self):
        self.assertEqual(
            self.admin_client.post(URL, self.payload(), format="json").status_code, 201
        )
        response = self.admin_client.post(URL, self.payload(), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "ATTENDANCE_ALREADY_RECORDED")

    def test_one_record_per_day_but_different_projects_is_allowed(self):
        created = self.admin_client.post(URL, self.payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        ProjectWorker.objects.create(project=self.other_project, worker=self.worker)
        response = self.admin_client.post(
            URL, self.payload(project=self.other_project.pk), format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_punch_out_can_be_added_later(self):
        record = self.admin_client.post(
            URL,
            self.payload(punch_in=punch_on(today, 9).isoformat(), punch_out=None),
            format="json",
        ).data
        self.assertIsNone(record["punch_out"])
        self.assertTrue(record["is_open"])
        response = self.admin_client.patch(
            f"{URL}{record['id']}/",
            {"punch_out": punch_on(today, 18).isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        # Nine on-site hours minus the one-hour lunch = eight.
        self.assertEqual(response.data["work_hours"], 8.0)
        self.assertFalse(response.data["is_open"])

    def test_filters(self):
        self.admin_client.post(URL, self.payload(), format="json")
        self.admin_client.post(
            URL,
            self.payload(
                worker=self.plain.pk,
                project=self.other_project.pk,
                date=(today - timedelta(days=1)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(
            self.admin_client.get(URL, {"project": self.other_project.pk}).data["count"], 1
        )
        self.assertEqual(self.admin_client.get(URL, {"date": today.isoformat()}).data["count"], 1)
        self.assertEqual(
            self.admin_client.get(URL, {"date_from": (today - timedelta(days=1)).isoformat()}).data[
                "count"
            ],
            2,
        )
        self.assertEqual(
            self.admin_client.get(URL, {"date_to": (today - timedelta(days=1)).isoformat()}).data[
                "count"
            ],
            1,
        )
        self.assertEqual(self.admin_client.get(URL, {"worker": self.plain.pk}).data["count"], 1)

    def test_audit_entries_written(self):
        from apps.audit.models import AuditLog

        self.admin_client.post(URL, self.payload(), format="json")
        self.assertTrue(AuditLog.objects.filter(action="ATTENDANCE_MARKED").exists())
