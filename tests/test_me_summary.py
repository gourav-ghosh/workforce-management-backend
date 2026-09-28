"""Worker-facing summary endpoint tests."""

from datetime import date

from apps.tools.models import Tool, ToolAssignment
from tests.utils import BaseAPITestCase


class MeSummaryTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.tool_good = Tool.objects.create(tool_id="T-SUM-1", name="Good tool")
        self.tool_damaged = Tool.objects.create(
            tool_id="T-SUM-2",
            name="Damaged tool",
            availability_status=Tool.AvailabilityStatus.DAMAGED,
        )
        self.tool_undamaged = Tool.objects.create(tool_id="T-SUM-3", name="Undamaged")
        ToolAssignment.objects.create(
            tool=self.tool_good,
            worker=self.worker,
            issue_date=date.today(),
            issue_condition=Tool.Condition.GOOD,
        )
        ToolAssignment.objects.create(
            tool=self.tool_damaged,
            worker=self.worker,
            issue_date=date.today(),
            issue_condition=Tool.Condition.GOOD,
        )
        ToolAssignment.objects.create(
            tool=self.tool_undamaged,
            worker=self.worker,
            issue_date=date.today(),
            issue_condition=Tool.Condition.GOOD,
        )

    def test_summary_reports_damaged_active_tools(self):
        response = self.worker_client.get("/api/v1/me/summary/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["tools"], 3)
        self.assertEqual(response.data["tools_damaged"], 1)
