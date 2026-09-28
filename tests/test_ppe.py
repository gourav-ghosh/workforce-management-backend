"""PPE CRUD + issue/return/history workflow tests."""

from apps.audit.models import AuditLog
from apps.ppe.models import PPE, PPEAssignment
from tests.utils import BaseAPITestCase

PPE_URL = "/api/v1/ppe/"


class PPECrudTests(BaseAPITestCase):
    def test_create_ppe_item(self):
        response = self.admin_client.post(
            PPE_URL,
            {
                "ppe_id": "PPE-900",
                "ppe_type": "HELMET",
                "name": "White Helmet",
                "size": "Free",
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        item = PPE.objects.get(ppe_id="PPE-900")
        self.assertEqual(item.ppe_type, PPE.PPEType.HELMET)

    def test_expiry_must_follow_purchase(self):
        response = self.admin_client.post(
            PPE_URL,
            {
                "ppe_id": "PPE-901",
                "ppe_type": "GLOVES",
                "name": "Bad Dates Gloves",
                "purchase_date": "2026-06-01",
                "expiry_date": "2026-05-01",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_blocked_with_history(self):
        item = PPE.objects.create(ppe_id="PPE-902", ppe_type="SHOES", name="Old Boots")
        PPEAssignment.objects.create(
            ppe=item,
            worker=self.worker,
            issue_date="2026-01-01",
            issue_condition=PPE.Condition.GOOD,
        )
        response = self.admin_client.delete(f"{PPE_URL}{item.pk}/")
        self.assertEqual(response.status_code, 409)


class PPEIssueReturnTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.item = PPE.objects.create(
            ppe_id="PPE-910", ppe_type="JACKET", name="Reflective Jacket"
        )

    def test_issue_and_return_flow(self):
        issue = self.admin_client.post(
            f"{PPE_URL}{self.item.pk}/issue/",
            {"worker_id": self.worker.pk},
        )
        self.assertEqual(issue.status_code, 201, issue.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.availability_status, PPE.AvailabilityStatus.ASSIGNED)
        self.assertTrue(AuditLog.objects.filter(action="PPE_ISSUED").exists())

        ret = self.admin_client.post(
            f"{PPE_URL}{self.item.pk}/return/", {"return_condition": "FAIR"}
        )
        self.assertEqual(ret.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.availability_status, PPE.AvailabilityStatus.AVAILABLE)
        self.assertTrue(AuditLog.objects.filter(action="PPE_RETURNED").exists())

    def test_double_issue_conflicts(self):
        self.admin_client.post(f"{PPE_URL}{self.item.pk}/issue/", {"worker_id": self.worker.pk})
        again = self.admin_client.post(
            f"{PPE_URL}{self.item.pk}/issue/", {"worker_id": self.other_worker.pk}
        )
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.data["code"], "PPE_NOT_AVAILABLE")

    def test_return_without_assignment_conflicts(self):
        response = self.admin_client.post(
            f"{PPE_URL}{self.item.pk}/return/", {"return_condition": "GOOD"}
        )
        self.assertEqual(response.status_code, 409)

    def test_return_damaged_marks_ppe_damaged(self):
        self.admin_client.post(f"{PPE_URL}{self.item.pk}/issue/", {"worker_id": self.worker.pk})
        self.admin_client.post(f"{PPE_URL}{self.item.pk}/return/", {"return_condition": "DAMAGED"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.availability_status, PPE.AvailabilityStatus.DAMAGED)

    def test_history_preserved(self):
        PPEAssignment.objects.create(
            ppe=self.item,
            worker=self.worker,
            issue_date="2026-03-01",
            expected_return_date="2026-04-01",
            return_date="2026-03-28",
            issue_condition=PPE.Condition.GOOD,
            return_condition=PPE.Condition.GOOD,
            status=PPEAssignment.Status.RETURNED,
        )
        self.admin_client.post(
            f"{PPE_URL}{self.item.pk}/issue/", {"worker_id": self.other_worker.pk}
        )
        history = self.admin_client.get(f"{PPE_URL}{self.item.pk}/history/")
        self.assertEqual(history.data["count"], 2)


class PPESearchTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.helmet = PPE.objects.create(ppe_id="PPE-920", ppe_type="HELMET", name="White Helmet")
        self.boots = PPE.objects.create(ppe_id="PPE-921", ppe_type="SHOES", name="Steel Boots")

    def test_search_by_id_name_type(self):
        response = self.admin_client.get(PPE_URL, {"search": "helmet"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["ppe_id"], "PPE-920")

        response = self.admin_client.get(PPE_URL, {"ppe_type": "SHOES"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Steel Boots")
