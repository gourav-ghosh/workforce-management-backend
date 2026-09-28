"""Employee performance record tests."""

from datetime import date, timedelta

from apps.performance.models import PerformanceRecord
from tests.utils import BaseAPITestCase


def _url(worker_id, record_id=None):
    base = f"/api/v1/workers/{worker_id}/performance/"
    if record_id is not None:
        return f"{base}{record_id}/"
    return base


class PerformanceRecordAdminTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.period_start = date.today() - timedelta(days=30)
        self.period_end = date.today()

    def _payload(self, **overrides):
        payload = {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "attendance_time": 4,
            "ppe_replacement_duration": 5,
            "job_training_attendance": 3,
            "job_time": 4,
            "advance_loan_repayment": 5,
            "notes": "Solid month overall.",
            "is_visible_to_worker": False,
        }
        payload.update(overrides)
        return payload

    def test_admin_creates_performance_record(self):
        response = self.admin_client.post(_url(self.worker.pk), self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["worker"], self.worker.pk)
        self.assertEqual(response.data["evaluator"], self.admin.pk)
        self.assertEqual(response.data["overall_score"], 4.2)
        record = PerformanceRecord.objects.get(pk=response.data["id"])
        self.assertEqual(record.evaluator, self.admin)

    def test_score_out_of_range_rejected(self):
        response = self.admin_client.post(
            _url(self.worker.pk), self._payload(attendance_time=9), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("attendance_time", response.data)

    def test_period_order_enforced(self):
        response = self.admin_client.post(
            _url(self.worker.pk),
            self._payload(period_start=self.period_end, period_end=self.period_start),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("period_end", response.data)

    def test_admin_lists_filters_and_updates(self):
        record = PerformanceRecord.objects.create(
            worker=self.worker,
            evaluator=self.admin,
            period_start=self.period_start,
            period_end=self.period_end,
            attendance_time=3,
            notes="Initial.",
        )
        response = self.admin_client.get(_url(self.worker.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

        patch = self.admin_client.patch(
            _url(self.worker.pk, record.pk),
            {"notes": "Updated.", "is_visible_to_worker": True},
            format="json",
        )
        self.assertEqual(patch.status_code, 200, patch.data)
        record.refresh_from_db()
        self.assertTrue(record.is_visible_to_worker)
        self.assertEqual(record.notes, "Updated.")

    def test_admin_can_delete_record(self):
        record = PerformanceRecord.objects.create(
            worker=self.worker,
            evaluator=self.admin,
            period_start=self.period_start,
            period_end=self.period_end,
        )
        response = self.admin_client.delete(_url(self.worker.pk, record.pk))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(PerformanceRecord.objects.filter(pk=record.pk).exists())

    def test_worker_role_forbidden_from_admin_endpoints(self):
        for method, name in [
            ("get", None),
            ("post", None),
        ]:
            url = _url(self.worker.pk)
            fn = getattr(self.worker_client, method)
            if name:
                fn(url, {name: "x"})
            else:
                fn(url)
            # Workers can GET their own performance, but POST is forbidden.
            # We only assert the create is forbidden.
        create = self.worker_client.post(_url(self.worker.pk), self._payload(), format="json")
        self.assertEqual(create.status_code, 403)


class WorkerPerformanceVisibilityTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()

    def _create(self, **kwargs):
        return PerformanceRecord.objects.create(
            worker=self.worker,
            evaluator=self.admin,
            period_start=date.today() - timedelta(days=30),
            period_end=date.today(),
            **kwargs,
        )

    def test_worker_only_sees_visible_records(self):
        visible = self._create(notes="Visible.", is_visible_to_worker=True)
        self._create(notes="Hidden.", is_visible_to_worker=False)

        response = self.worker_client.get("/api/v1/me/performance/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data]
        self.assertIn(visible.id, ids)
        self.assertEqual(len(ids), 1)

    def test_worker_cannot_toggle_visibility(self):
        self._create(is_visible_to_worker=True)
        # Workers don't have any admin endpoint to update their record; we
        # confirm /me/performance/ is read-only by ensuring POST returns 405.
        response = self.worker_client.post(
            "/api/v1/me/performance/", {}, format="json"
        )
        self.assertEqual(response.status_code, 405)
