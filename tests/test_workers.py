"""Worker management CRUD, search and permission tests."""

from rest_framework.test import APIClient

from tests.utils import BaseAPITestCase

WORKER_LIST_URL = "/api/v1/workers/"


class WorkerCrudTests(BaseAPITestCase):
    def test_admin_can_create_worker_with_account(self):
        payload = {
            "employee_id": "EMP100",
            "full_name": "New Worker",
            "phone_number": "+91 91111 11111",
            "designation": "Welder",
            "employment_status": "ACTIVE",
            "username": "newworker",
            "password": "Str0ngPass!x",
        }
        response = self.admin_client.post(WORKER_LIST_URL, payload, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["employee_id"], "EMP100")

        from apps.accounts.models import User

        user = User.objects.get(username="newworker")
        self.assertEqual(user.role, User.Role.WORKER)
        self.assertTrue(user.check_password("Str0ngPass!x"))

    def test_create_worker_requires_username_and_password(self):
        response = self.admin_client.post(
            WORKER_LIST_URL,
            {"employee_id": "EMP101", "full_name": "No Account", "phone_number": "123"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)

    def test_duplicate_username_rejected(self):
        payload = {
            "employee_id": "EMP102",
            "full_name": "Dup User",
            "phone_number": "+91 92222 22222",
            "username": "worker1",  # already exists
            "password": "Str0ngPass!x",
        }
        response = self.admin_client.post(WORKER_LIST_URL, payload, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)

    def test_update_worker_and_employment_status_deactivates_user(self):
        url = f"{WORKER_LIST_URL}{self.worker.pk}/"
        response = self.admin_client.patch(
            url, {"employment_status": "INACTIVE"}, format="multipart"
        )
        self.assertEqual(response.status_code, 200)

        self.worker.user.refresh_from_db()
        self.assertFalse(self.worker.user.is_active)

    def test_reset_password_action(self):
        url = f"{WORKER_LIST_URL}{self.worker.pk}/reset-password/"
        response = self.admin_client.post(url, {"new_password": "FreshPass@77"})
        self.assertEqual(response.status_code, 200)
        self.worker.user.refresh_from_db()
        self.assertTrue(self.worker.user.check_password("FreshPass@77"))

    def test_delete_blocked_when_history_exists(self):
        from apps.tools.models import Tool, ToolAssignment

        tool = Tool.objects.create(tool_id="T-DEL-1", name="History Tool")
        ToolAssignment.objects.create(
            tool=tool,
            worker=self.worker,
            issue_date="2026-07-01",
            issue_condition=Tool.Condition.GOOD,
        )
        response = self.admin_client.delete(f"{WORKER_LIST_URL}{self.worker.pk}/")
        self.assertEqual(response.status_code, 409)

    def test_delete_allowed_when_no_history(self):
        response = self.admin_client.delete(f"{WORKER_LIST_URL}{self.other_worker.pk}/")
        self.assertEqual(response.status_code, 204)


class WorkerSearchTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.make_worker(username="worker3", employee_id="EMP003", full_name="Zara Khan")
        self.make_worker(
            username="worker4",
            employee_id="EMP004",
            full_name="Mohan Lal",
            employment_status="INACTIVE",
        )

    def test_search_by_name_employee_id_phone(self):
        response = self.admin_client.get(WORKER_LIST_URL, {"search": "Zara"})
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["employee_id"], "EMP003")

        response = self.admin_client.get(WORKER_LIST_URL, {"search": "EMP004"})
        self.assertEqual(len(response.data["results"]), 1)

        # Phone search: all fixtures share prefix; use unique suffix approach
        response = self.admin_client.get(WORKER_LIST_URL, {"search": "+91 90000"})
        self.assertGreaterEqual(len(response.data["results"]), 3)

    def test_filter_by_status(self):
        response = self.admin_client.get(WORKER_LIST_URL, {"status": "INACTIVE"})
        results = response.data["results"]
        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(all(row["employment_status"] == "INACTIVE" for row in results))

    def test_list_is_paginated(self):
        response = self.admin_client.get(WORKER_LIST_URL)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)

    def test_worker_role_cannot_list(self):
        client = APIClient()
        client.force_authenticate(user=self.worker.user)
        response = client.get(WORKER_LIST_URL)
        self.assertEqual(response.status_code, 403)
