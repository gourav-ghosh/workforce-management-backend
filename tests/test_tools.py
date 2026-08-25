"""Tool CRUD + issue/return/damage/history workflow tests."""

from apps.audit.models import AuditLog
from apps.tools.models import Tool, ToolAssignment, ToolDamage
from tests.utils import BaseAPITestCase

TOOLS_URL = "/api/v1/tools/"


class ToolCrudTests(BaseAPITestCase):
    def test_create_and_update_tool(self):
        create = self.admin_client.post(
            TOOLS_URL,
            {"tool_id": "T-500", "name": "Drill Press", "category": "Power Tools"},
        )
        self.assertEqual(create.status_code, 201)
        tool_id = create.data["id"]

        patch = self.admin_client.patch(f"{TOOLS_URL}{tool_id}/", {"condition": "FAIR"})
        self.assertEqual(patch.status_code, 200)

    def test_delete_blocked_with_history(self):
        tool = Tool.objects.create(tool_id="T-501", name="Old Saw")
        ToolAssignment.objects.create(
            tool=tool,
            worker=self.worker,
            issue_date="2026-01-01",
            issue_condition=Tool.Condition.GOOD,
            status=ToolAssignment.Status.RETURNED,
        )
        response = self.admin_client.delete(f"{TOOLS_URL}{tool.pk}/")
        self.assertEqual(response.status_code, 409)


class ToolIssueReturnTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        from apps.projects.models import Project

        self.tool = Tool.objects.create(tool_id="T-600", name="Angle Grinder")
        self.project = Project.objects.create(project_number="PRJ-T-1", project_name="P")

    def issue(self, worker_id=None, **overrides):
        payload = {"worker_id": worker_id or self.worker.pk}
        payload.update(overrides)
        return self.admin_client.post(f"{TOOLS_URL}{self.tool.pk}/assign/", payload)

    def test_issue_sets_status_and_creates_active_assignment(self):
        response = self.issue()
        self.assertEqual(response.status_code, 201, response.data)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.availability_status, Tool.AvailabilityStatus.ASSIGNED)
        assignment = ToolAssignment.objects.get(pk=response.data["assignment_id"])
        self.assertEqual(assignment.status, ToolAssignment.Status.ACTIVE)
        self.assertTrue(AuditLog.objects.filter(action="TOOL_ISSUED").exists())

    def test_double_issue_rejected(self):
        self.issue()
        second = self.issue(worker_id=self.other_worker.pk)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.data["code"], "TOOL_NOT_AVAILABLE")

    def test_active_assignment_unique_constraint_enforced(self):
        """DB-level guarantee: a second ACTIVE row violates the constraint."""
        from datetime import date

        from django.db import IntegrityError, transaction

        ToolAssignment.objects.create(
            tool=self.tool,
            worker=self.worker,
            issue_date=date.today(),
            issue_condition=Tool.Condition.GOOD,
        )
        self.tool.availability_status = Tool.AvailabilityStatus.ASSIGNED
        self.tool.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ToolAssignment.objects.create(
                tool=self.tool,
                worker=self.other_worker,
                issue_date=date.today(),
                issue_condition=Tool.Condition.GOOD,
            )

    def test_concurrent_issue_only_one_assignment_survives(self):
        """Service-level race guard: only one active assignment can exist.

        Uses two sequential service calls through separate transactions to
        stay deterministic on all database backends; the unique constraint
        test above proves the database enforces it under true concurrency.
        """
        from django.db import transaction as db_transaction

        from apps.tools import services

        services.issue_tool(actor=self.admin, tool_id=self.tool.pk, worker_id=self.worker.pk)
        with self.assertRaises(Exception), db_transaction.atomic():
            services.issue_tool(
                actor=self.admin, tool_id=self.tool.pk, worker_id=self.other_worker.pk
            )

        active = self.tool.assignments.filter(status=ToolAssignment.Status.ACTIVE).count()
        self.assertEqual(active, 1)

    def test_return_flow_good_condition(self):
        issue_response = self.issue(expected_return_date="2026-12-31")
        response = self.admin_client.post(
            f"{TOOLS_URL}{self.tool.pk}/return/",
            {"return_condition": "GOOD"},
        )
        self.assertEqual(response.status_code, 200)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.availability_status, Tool.AvailabilityStatus.AVAILABLE)
        assignment = ToolAssignment.objects.get(pk=issue_response.data["assignment_id"])
        self.assertEqual(assignment.status, ToolAssignment.Status.RETURNED)
        self.assertIsNotNone(assignment.return_date)
        self.assertTrue(AuditLog.objects.filter(action="TOOL_RETURNED").exists())

    def test_return_damaged_sets_tool_damaged(self):
        self.issue()
        response = self.admin_client.post(
            f"{TOOLS_URL}{self.tool.pk}/return/",
            {"return_condition": "DAMAGED", "remarks": "Housing cracked"},
        )
        self.assertEqual(response.status_code, 200)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.availability_status, Tool.AvailabilityStatus.DAMAGED)

    def test_return_without_assignment_conflicts(self):
        response = self.admin_client.post(
            f"{TOOLS_URL}{self.tool.pk}/return/", {"return_condition": "GOOD"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "NO_ACTIVE_ASSIGNMENT")

    def test_invalid_expected_return_date(self):
        response = self.issue(issue_date="2026-08-10", expected_return_date="2026-08-01")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "INVALID_DATE_RANGE")


class ToolDamageTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.tool = Tool.objects.create(tool_id="T-700", name="Cutting Torch")

    def test_damage_record_updates_status_and_audits(self):
        response = self.admin_client.post(
            f"{TOOLS_URL}{self.tool.pk}/damage/",
            {
                "damage_description": "Hose leak near valve",
                "damage_condition": "DAMAGED",
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.availability_status, Tool.AvailabilityStatus.DAMAGED)
        damage = ToolDamage.objects.get(pk=response.data["id"])
        self.assertEqual(damage.repair_status, ToolDamage.RepairStatus.REPORTED)
        self.assertTrue(AuditLog.objects.filter(action="TOOL_DAMAGED").exists())


class ToolHistoryTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.tool = Tool.objects.create(tool_id="T-800", name="History Drill")

    def _issue_and_return(self, worker, days_ago):
        from datetime import date, timedelta

        issue_day = date.today() - timedelta(days=days_ago)
        assignment = ToolAssignment.objects.create(
            tool=self.tool,
            worker=worker,
            issue_date=issue_day,
            expected_return_date=issue_day + timedelta(days=5),
            return_date=issue_day + timedelta(days=3),
            issue_condition=Tool.Condition.GOOD,
            return_condition=Tool.Condition.FAIR,
            status=ToolAssignment.Status.RETURNED,
        )
        return assignment

    def test_history_preserved_after_new_assignments(self):
        first = self._issue_and_return(self.worker, days_ago=30)
        second = self._issue_and_return(self.other_worker, days_ago=10)

        response = self.admin_client.get(f"{TOOLS_URL}{self.tool.pk}/history/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(first.id, ids)
        self.assertIn(second.id, ids)
        # newest first ordering
        self.assertLess(ids.index(second.id), ids.index(first.id))

    def test_full_lifecycle_via_api_retains_records(self):
        # issue -> return -> issue again -> all rows retained
        self.admin_client.post(f"{TOOLS_URL}{self.tool.pk}/assign/", {"worker_id": self.worker.pk})
        self.admin_client.post(f"{TOOLS_URL}{self.tool.pk}/return/", {"return_condition": "GOOD"})
        self.admin_client.post(
            f"{TOOLS_URL}{self.tool.pk}/assign/", {"worker_id": self.other_worker.pk}
        )
        history = self.admin_client.get(f"{TOOLS_URL}{self.tool.pk}/history/")
        self.assertEqual(history.data["count"], 2)


class ToolSearchFilterTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.drill = Tool.objects.create(
            tool_id="T-901", name="Hammer Drill", category="Power Tools"
        )
        self.saw = Tool.objects.create(tool_id="T-902", name="Circular Saw", category="Power Tools")
        self.wrench = Tool.objects.create(
            tool_id="T-903", name="Pipe Wrench", category="Hand Tools"
        )

    def test_search_by_name_and_code(self):
        response = self.admin_client.get(TOOLS_URL, {"search": "drill"})
        names = [row["name"] for row in response.data["results"]]
        self.assertIn("Hammer Drill", names)
        self.assertNotIn("Pipe Wrench", names)

        response = self.admin_client.get(TOOLS_URL, {"search": "T-903"})
        self.assertEqual(response.data["results"][0]["name"], "Pipe Wrench")

    def test_filter_by_status_and_category(self):
        self.drill.availability_status = Tool.AvailabilityStatus.ASSIGNED
        self.drill.save()

        response = self.admin_client.get(TOOLS_URL, {"status": "ASSIGNED"})
        self.assertEqual([row["id"] for row in response.data["results"]], [self.drill.id])

        response = self.admin_client.get(TOOLS_URL, {"category": "Hand Tools"})
        self.assertEqual(response.data["count"], 1)
