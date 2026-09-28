"""Tool repair workflow tests (admin marks a damaged tool repaired)."""

from datetime import date

from apps.tools.models import Tool, ToolAssignment, ToolDamage
from tests.utils import BaseAPITestCase

TOOLS_URL = "/api/v1/tools/"


class ToolRepairTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.tool = Tool.objects.create(tool_id="T-RPR-1", name="Repaired tool")

    def test_repair_closes_damage_and_marks_available(self):
        assignment = ToolAssignment.objects.create(
            tool=self.tool,
            worker=self.worker,
            issue_date=date.today(),
            issue_condition=Tool.Condition.GOOD,
        )
        ToolDamage.objects.create(
            tool=self.tool,
            assignment=assignment,
            damage_date=date.today(),
            damage_description="Hammer head loose.",
            damage_condition=Tool.Condition.DAMAGED,
            repair_status=ToolDamage.RepairStatus.REPORTED,
        )
        self.tool.availability_status = Tool.AvailabilityStatus.DAMAGED
        self.tool.save()

        response = self.admin_client.post(
            f"{TOOLS_URL}{self.tool.pk}/repair/",
            {
                "condition": "GOOD",
                "close_assignment": True,
                "notes": "Hammer head reattached.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.tool.refresh_from_db()
        self.tool.availability_status = Tool.AvailabilityStatus.AVAILABLE
        # verify damage is closed
        damages = list(self.tool.damages.all())
        self.assertTrue(all(d.repair_status == ToolDamage.RepairStatus.COMPLETED for d in damages))
        # assignment closed
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, ToolAssignment.Status.RETURNED)

    def test_repair_without_close_assignment_leaves_tool_damaged(self):
        # With close_assignment=False the assignment stays active. The tool
        # status is only set back to AVAILABLE when no active assignment
        # remains; the admin is expected to set ASSIGNED explicitly via
        # the issue flow. The damage records are still closed.
        assignment = ToolAssignment.objects.create(
            tool=self.tool,
            worker=self.worker,
            issue_date=date.today(),
            issue_condition=Tool.Condition.GOOD,
        )
        ToolDamage.objects.create(
            tool=self.tool,
            assignment=assignment,
            damage_date=date.today(),
            damage_description="Hose leak",
            damage_condition=Tool.Condition.DAMAGED,
        )
        self.tool.availability_status = Tool.AvailabilityStatus.DAMAGED
        self.tool.save()

        response = self.admin_client.post(
            f"{TOOLS_URL}{self.tool.pk}/repair/",
            {"condition": "GOOD", "close_assignment": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.tool.refresh_from_db()
        # Damage record is closed.
        damages = list(self.tool.damages.all())
        self.assertTrue(all(d.repair_status == ToolDamage.RepairStatus.COMPLETED for d in damages))
        # Tool status stays DAMAGED because an active assignment exists.
        self.assertEqual(self.tool.availability_status, Tool.AvailabilityStatus.DAMAGED)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, ToolAssignment.Status.ACTIVE)

    def test_repair_rejects_invalid_condition(self):
        response = self.admin_client.post(
            f"{TOOLS_URL}{self.tool.pk}/repair/",
            {"condition": "UNOBTAINABLE"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_repair_requires_admin(self):
        response = self.worker_client.post(
            f"{TOOLS_URL}{self.tool.pk}/repair/",
            {"condition": "GOOD"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
