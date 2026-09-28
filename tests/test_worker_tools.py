"""Worker-facing tool history + damage reporting tests."""

from datetime import date, timedelta

from apps.tools.models import Tool, ToolAssignment, ToolDamage, ToolMedia
from tests.utils import BaseAPITestCase, make_image_file

TOOLS_URL = "/api/v1/tools/"


class WorkerToolHistoryTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.tool = Tool.objects.create(tool_id="T-WH-1", name="History Tool")

    def _make_assignment(self, worker, *, days_ago, status, condition="GOOD"):
        is_returned = status == ToolAssignment.Status.RETURNED
        return ToolAssignment.objects.create(
            tool=self.tool,
            worker=worker,
            issue_date=date.today() - timedelta(days=days_ago),
            issue_condition=Tool.Condition.GOOD,
            return_date=(
                date.today() - timedelta(days=max(days_ago - 2, 0))
                if is_returned
                else None
            ),
            return_condition=Tool.Condition.FAIR if is_returned else None,
            status=status,
        )

    def test_history_returns_active_and_past_assignments(self):
        self._make_assignment(self.worker, days_ago=30, status=ToolAssignment.Status.RETURNED)
        self._make_assignment(self.other_worker, days_ago=5, status=ToolAssignment.Status.ACTIVE)

        # Admin endpoint includes the active assignment for the other worker.
        admin_response = self.admin_client.get(f"{TOOLS_URL}{self.tool.pk}/history/")
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.data["count"], 2)

        # Worker sees only their own assignments via /me/tools/history/.
        worker_response = self.worker_client.get("/api/v1/me/tools/history/")
        self.assertEqual(worker_response.status_code, 200)
        self.assertEqual(worker_response.data["count"], 1)
        self.assertEqual(worker_response.data["results"][0]["worker"], self.worker.pk)

    def test_history_includes_damage_records_and_media(self):
        assignment = self._make_assignment(
            self.worker, days_ago=20, status=ToolAssignment.Status.RETURNED
        )
        damage = ToolDamage.objects.create(
            tool=self.tool,
            assignment=assignment,
            damage_date=date.today() - timedelta(days=18),
            damage_description="Hose burst during operation.",
            damage_condition=Tool.Condition.DAMAGED,
        )
        ToolMedia.objects.create(
            tool=self.tool,
            damage=damage,
            media_type=ToolMedia.MediaType.DAMAGE,
            file=make_image_file("damage.png"),
        )
        ToolMedia.objects.create(
            tool=self.tool,
            assignment=assignment,
            media_type=ToolMedia.MediaType.ISSUE,
            file=make_image_file("issue.png"),
        )

        response = self.worker_client.get("/api/v1/me/tools/history/")
        self.assertEqual(response.status_code, 200)
        record = response.data["results"][0]
        self.assertEqual(len(record["damages"]), 1)
        self.assertEqual(record["damages"][0]["description"], "Hose burst during operation.")
        self.assertEqual(len(record["damages"][0]["media"]), 1)
        self.assertTrue(record["damages"][0]["media"][0]["file_url"].endswith(".png"))
        self.assertEqual(len(record["media"]), 1)


class WorkerToolDamageReportTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.tool = Tool.objects.create(tool_id="T-WD-1", name="Reporter Tool")
        self.assignment = ToolAssignment.objects.create(
            tool=self.tool,
            worker=self.worker,
            issue_date=date.today(),
            issue_condition=Tool.Condition.GOOD,
        )

    def test_worker_can_report_damage_against_own_assignment(self):
        url = f"/api/v1/me/tools/{self.assignment.pk}/damage/"
        response = self.worker_client.post(
            url,
            {
                "damage_description": "Bit broke off mid-job.",
                "damage_condition": "DAMAGED",
                "remarks": "Stopped work immediately.",
                "photos": [make_image_file("self.png")],
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["media"]), 1)

        damage = ToolDamage.objects.get(pk=response.data["id"])
        self.assertEqual(damage.assignment_id, self.assignment.pk)
        self.assertEqual(damage.repair_status, ToolDamage.RepairStatus.REPORTED)
        # Tool is automatically marked damaged so it isn't re-issued.
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.availability_status, Tool.AvailabilityStatus.DAMAGED)

    def test_worker_cannot_report_damage_against_another_workers_assignment(self):
        # Move the existing self.worker assignment out of the way so a new
        # ACTIVE assignment for other_worker on the same tool is allowed.
        self.assignment.status = ToolAssignment.Status.RETURNED
        self.assignment.return_date = date.today()
        self.assignment.return_condition = Tool.Condition.GOOD
        self.assignment.save()

        other_assignment = ToolAssignment.objects.create(
            tool=self.tool,
            worker=self.other_worker,
            issue_date=date.today(),
            issue_condition=Tool.Condition.GOOD,
        )
        url = f"/api/v1/me/tools/{other_assignment.pk}/damage/"
        response = self.worker_client.post(
            url,
            {
                "damage_description": "Not my tool",
                "damage_condition": "DAMAGED",
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "WORKER_DATA_ISOLATION")

    def test_worker_tool_detail_returns_nested_damage(self):
        damage = ToolDamage.objects.create(
            tool=self.tool,
            assignment=self.assignment,
            damage_date=date.today(),
            damage_description="Test damage",
            damage_condition=Tool.Condition.DAMAGED,
        )
        ToolMedia.objects.create(
            tool=self.tool,
            damage=damage,
            media_type=ToolMedia.MediaType.DAMAGE,
            file=make_image_file("d.png"),
        )
        response = self.worker_client.get(f"/api/v1/me/tools/{self.assignment.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["damages"]), 1)
        self.assertEqual(len(response.data["damages"][0]["media"]), 1)
