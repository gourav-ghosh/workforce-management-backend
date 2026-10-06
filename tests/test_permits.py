"""TBM & work-permit tests.

Mirrors the attendance test suite so the two modules stay predictable: scope
rules for admin vs supervisor, the daily date window, duplicate handling, and
the two optional sheet attachments.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from django.test import override_settings
from django.utils import timezone as django_timezone

from apps.accounts.models import User
from apps.permits.models import WorkPermit, today_in_permits_tz
from apps.projects.models import Project, ProjectWorker
from apps.workers.models import WorkerProfile
from tests.utils import BaseAPITestCase, make_image_file

URL = "/api/v1/permits/"
today = today_in_permits_tz()

# Permit sheets are documents, but a small PNG exercises the same validation
# path without embedding a real PDF.
DOCUMENT_NAME = "permit.png"


def make_project(number="PRJ-WP-1", name="Permit Project"):
    return Project.objects.create(project_number=number, project_name=name)


def _pk(value):
    """Accept a model instance or a bare id."""
    return getattr(value, "pk", value)


def permit_payload(project=None, worker=None, **overrides):
    data = {
        # `date` reads the module global at call time, so it stays correct
        # after setUp re-anchors `today`.
        "date": today.isoformat(),
        "work_permit_number": "WP-1001",
    }
    if project is not None:
        data["project"] = _pk(project)
    if worker is not None:
        data["worker"] = _pk(worker)
    data.update(overrides)
    return data


class WorkPermitTestBase(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        # The service resolves "today" per request in the business timezone;
        # re-anchor so a run that straddles midnight does not fail spuriously.
        global today
        today = today_in_permits_tz()
        self.project = make_project()
        ProjectWorker.objects.create(project=self.project, worker=self.worker)
        self.plain = self.make_worker(employee_id="EMP-WP1", mobile_number="+91 90000 31001")
        ProjectWorker.objects.create(project=self.project, worker=self.plain)
        self.sup_user = User.objects.create_user(
            mobile_number="+91 90000 32000", password="Work@12345", role="WORKER"
        )
        self.supervisor = WorkerProfile.objects.create(
            user=self.sup_user,
            employee_id="SUP-WP1",
            full_name="WP Supervisor",
            phone_number="+91 90000 32000",
            is_supervisor=True,
        )
        ProjectWorker.objects.create(project=self.project, worker=self.supervisor)
        self.sup_client = self.client_for(self.sup_user)

    def payload(self, project=None, worker=None, **overrides):
        """A valid payload for the shared project/worker, or an override."""
        return permit_payload(project or self.project, worker or self.worker, **overrides)


@override_settings(PERMIT_MAX_BACKDATE_DAYS=2, ATTENDANCE_TIMEZONE="Asia/Kolkata")
class WorkPermitScopeTests(WorkPermitTestBase):
    def test_supervisor_can_raise_for_worker_on_their_project(self):
        response = self.sup_client.post(URL, self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["work_permit_number"], "WP-1001")

    def test_supervisor_blocked_outside_their_projects(self):
        other = make_project("PRJ-WP-OTHER")
        ProjectWorker.objects.create(project=other, worker=self.plain)
        response = self.sup_client.post(
            URL, self.payload(project=other, worker=self.plain), format="json"
        )
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "SUPERVISOR_OUT_OF_SCOPE")

    def test_supervisor_requires_worker_on_project(self):
        orphan = self.make_worker(employee_id="EMP-WP-ORPHAN", mobile_number="+91 90000 31099")
        response = self.sup_client.post(URL, self.payload(worker=orphan.pk), format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "WORKER_NOT_ON_PROJECT")

    def test_admin_can_raise_for_unassigned_worker(self):
        orphan = self.make_worker(employee_id="EMP-WP-ORPHAN2", mobile_number="+91 90000 31098")
        response = self.admin_client.post(URL, self.payload(worker=orphan.pk), format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_supervisor_list_is_scoped_to_their_projects(self):
        self.sup_client.post(URL, self.payload(), format="json")
        other = make_project("PRJ-WP-OTHER2")
        self.admin_client.post(URL, permit_payload(other, self.plain), format="json")
        response = self.sup_client.get(URL)
        self.assertEqual(response.data["count"], 1, "other project's permit is hidden")

    def test_admin_list_sees_everything(self):
        self.admin_client.post(URL, self.payload(), format="json")
        other = make_project("PRJ-WP-OTHER3")
        self.admin_client.post(URL, permit_payload(other, self.plain), format="json")
        self.assertEqual(self.admin_client.get(URL).data["count"], 2)

    def test_supervisor_cannot_read_a_permit_from_another_project(self):
        other = make_project("PRJ-WP-OTHER4")
        record = self.admin_client.post(URL, permit_payload(other, self.plain), format="json").data
        self.assertEqual(self.sup_client.get(f"{URL}{record['id']}/").status_code, 404)

    def test_plain_worker_has_no_access(self):
        self.assertEqual(self.worker_client.get(URL).status_code, 403)
        self.assertEqual(
            self.worker_client.post(URL, self.payload(), format="json").status_code,
            403,
        )

    def test_only_admin_can_delete(self):
        created = self.sup_client.post(URL, self.payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        detail = f"{URL}{created.data['id']}/"
        self.assertEqual(self.sup_client.delete(detail).status_code, 403)
        self.assertEqual(self.admin_client.delete(detail).status_code, 204)
        self.assertEqual(WorkPermit.objects.count(), 0)


@override_settings(PERMIT_MAX_BACKDATE_DAYS=2, ATTENDANCE_TIMEZONE="Asia/Kolkata")
class WorkPermitValidationTests(WorkPermitTestBase):
    def test_permit_number_is_required(self):
        response = self.admin_client.post(URL, self.payload(work_permit_number=""), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("work_permit_number", response.data)

    def test_project_and_worker_are_required_on_create(self):
        response = self.admin_client.post(
            URL,
            {"date": today.isoformat(), "work_permit_number": "WP-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("project", response.data)
        self.assertIn("worker", response.data)

    def test_date_is_required(self):
        response = self.admin_client.post(URL, {"work_permit_number": "WP-1"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("date", response.data)

    def test_both_sheets_are_optional(self):
        response = self.admin_client.post(URL, self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data["tbm_sheet_url"])
        self.assertIsNone(response.data["work_permit_sheet_url"])
        self.assertEqual(response.data["attachment_count"], 0)

    def test_sheets_can_be_uploaded(self):
        payload = self.payload()
        payload["tbm_sheet"] = make_image_file(name=DOCUMENT_NAME)
        payload["work_permit_sheet"] = make_image_file(name="permit2.png")
        response = self.admin_client.post(URL, payload, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["has_tbm_sheet"])
        self.assertTrue(response.data["has_work_permit_sheet"])
        self.assertEqual(response.data["attachment_count"], 2)
        self.assertIsNotNone(response.data["tbm_sheet_url"])
        self.assertIsNotNone(response.data["work_permit_sheet_url"])

    def test_only_the_tbm_sheet_can_be_uploaded(self):
        payload = self.payload()
        payload["tbm_sheet"] = make_image_file(name=DOCUMENT_NAME)
        response = self.admin_client.post(URL, payload, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["attachment_count"], 1)

    def test_duplicate_project_worker_date_rejected(self):
        self.assertEqual(
            self.admin_client.post(URL, self.payload(), format="json").status_code,
            201,
        )
        response = self.admin_client.post(URL, self.payload(), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "PERMIT_ALREADY_RECORDED")

    def test_same_worker_on_different_projects_is_allowed(self):
        self.admin_client.post(URL, self.payload(), format="json")
        other = make_project("PRJ-WP-DUP")
        ProjectWorker.objects.create(project=other, worker=self.worker)
        response = self.admin_client.post(URL, self.payload(project=other), format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_unknown_project_and_worker_are_rejected(self):
        # DRF's PrimaryKeyRelatedField rejects a bad id during field
        # validation, so this is a 400 rather than the service's 404. The
        # attendance module behaves the same way.
        missing_project = self.admin_client.post(URL, self.payload(project=999999), format="json")
        self.assertEqual(missing_project.status_code, 400)
        self.assertIn("project", missing_project.data)
        missing_worker = self.admin_client.post(URL, self.payload(worker=999999), format="json")
        self.assertEqual(missing_worker.status_code, 400)
        self.assertIn("worker", missing_worker.data)

    def test_filters(self):
        self.admin_client.post(URL, self.payload(), format="json")
        yesterday = today - dt.timedelta(days=1)
        payload = self.payload(worker=self.plain.pk)
        payload["date"] = yesterday.isoformat()
        self.admin_client.post(URL, payload, format="json")

        self.assertEqual(self.admin_client.get(URL, {"project": self.project.pk}).data["count"], 2)
        self.assertEqual(self.admin_client.get(URL, {"date": today.isoformat()}).data["count"], 1)
        self.assertEqual(self.admin_client.get(URL, {"worker": self.plain.pk}).data["count"], 1)
        self.assertEqual(
            self.admin_client.get(URL, {"date_from": yesterday.isoformat()}).data["count"],
            2,
        )


@override_settings(PERMIT_MAX_BACKDATE_DAYS=2, ATTENDANCE_TIMEZONE="Asia/Kolkata")
class WorkPermitDateWindowTests(WorkPermitTestBase):
    def test_today_is_allowed(self):
        self.assertEqual(
            self.admin_client.post(URL, self.payload(), format="json").status_code,
            201,
        )

    def test_two_days_back_is_allowed(self):
        response = self.admin_client.post(
            URL,
            self.payload(date=(today - dt.timedelta(days=2)).isoformat()),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_three_days_back_is_rejected(self):
        response = self.admin_client.post(
            URL,
            self.payload(date=(today - dt.timedelta(days=3)).isoformat()),
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "PERMIT_TOO_OLD")

    def test_future_date_is_rejected(self):
        response = self.admin_client.post(
            URL,
            self.payload(date=(today + dt.timedelta(days=1)).isoformat()),
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "PERMIT_FUTURE_DATE")


@override_settings(PERMIT_MAX_BACKDATE_DAYS=2, ATTENDANCE_TIMEZONE="Asia/Kolkata")
class WorkPermitUpdateTests(WorkPermitTestBase):
    def test_patch_can_correct_the_permit_number(self):
        created = self.admin_client.post(URL, self.payload(), format="json")
        detail = f"{URL}{created.data['id']}/"
        response = self.admin_client.patch(detail, {"work_permit_number": "WP-2002"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["work_permit_number"], "WP-2002")

    def test_patch_omitting_the_number_keeps_it(self):
        created = self.sup_client.post(URL, self.payload(), format="json")
        detail = f"{URL}{created.data['id']}/"
        response = self.sup_client.patch(detail, {"notes": "signed"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["work_permit_number"], "WP-1001")
        self.assertEqual(response.data["notes"], "signed")

    def test_patch_adding_a_sheet_after_the_fact(self):
        created = self.admin_client.post(URL, self.payload(), format="json")
        detail = f"{URL}{created.data['id']}/"
        response = self.admin_client.patch(
            detail,
            {"tbm_sheet": make_image_file(name=DOCUMENT_NAME)},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["has_tbm_sheet"])
        self.assertEqual(response.data["attachment_count"], 1)

    def test_supervisor_cannot_move_a_record_onto_another_project(self):
        created = self.sup_client.post(URL, self.payload(), format="json")
        detail = f"{URL}{created.data['id']}/"
        other = make_project("PRJ-WP-MOVE")
        response = self.sup_client.patch(detail, {"project": other.pk}, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "SUPERVISOR_OUT_OF_SCOPE")

    def test_patch_outside_the_date_window_is_rejected(self):
        created = self.admin_client.post(URL, self.payload(), format="json")
        detail = f"{URL}{created.data['id']}/"
        response = self.admin_client.patch(
            detail,
            {"date": (today - dt.timedelta(days=3)).isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "PERMIT_TOO_OLD")

    def test_duplicate_on_patch_is_rejected(self):
        self.admin_client.post(URL, self.payload(worker=self.plain.pk), format="json")
        created = self.admin_client.post(URL, self.payload(), format="json")
        detail = f"{URL}{created.data['id']}/"
        response = self.admin_client.patch(detail, {"worker": self.plain.pk}, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "PERMIT_ALREADY_RECORDED")


@override_settings(ATTENDANCE_TIMEZONE="Asia/Kolkata")
class WorkPermitModelTests(WorkPermitTestBase):
    def test_attachment_helpers(self):
        record = WorkPermit.objects.create(
            project=self.project,
            worker=self.worker,
            date=today,
            work_permit_number="WP-1",
        )
        self.assertFalse(record.has_tbm_sheet)
        self.assertEqual(record.attachment_count, 0)

    def test_recorded_by_is_set_from_the_actor(self):
        response = self.admin_client.post(URL, self.payload(), format="json")
        record = WorkPermit.objects.get(pk=response.data["id"])
        self.assertEqual(record.recorded_by_id, self.admin.id)
        self.assertEqual(response.data["recorded_by_name"], self.admin.mobile_number)

    def test_day_is_resolved_in_the_business_timezone(self):
        """The permit day must be the IST date, not the server's UTC date.

        Otherwise a permit raised at 20:00 UTC (01:30 the next day in IST)
        would be filed under the wrong working day.
        """
        ist = ZoneInfo("Asia/Kolkata")
        for _ in range(5):
            before = django_timezone.now()
            computed = today_in_permits_tz()
            after = django_timezone.now()
            if before.astimezone(ist).date() == after.astimezone(ist).date():
                self.assertEqual(computed, before.astimezone(ist).date())
                return
        # Only reachable in the vanishingly small window where the clock rolls
        # past IST midnight between the two reads.
        self.skipTest("run straddled the business-timezone midnight")
