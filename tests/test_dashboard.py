"""Dashboard aggregation and audit trail tests."""

from apps.ppe.models import PPE, PPEAssignment
from apps.projects.models import Project
from apps.tools.models import Tool, ToolAssignment
from apps.transportation.models import Vehicle
from tests.utils import BaseAPITestCase


class DashboardTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        from apps.workers.models import WorkerProfile

        self.make_worker(
            username="w-inactive",
            employee_id="EMP-INA",
            full_name="Inactive Person",
            employment_status=WorkerProfile.EmploymentStatus.INACTIVE,
        )

        Project.objects.create(
            project_number="D-1",
            project_name="Dash Active",
            status=Project.Status.ACTIVE,
        )
        Project.objects.create(
            project_number="D-2", project_name="Dash Draft", status=Project.Status.DRAFT
        )
        Tool.objects.create(
            tool_id="D-T1",
            name="Avail",
            availability_status=Tool.AvailabilityStatus.AVAILABLE,
        )
        Tool.objects.create(
            tool_id="D-T2",
            name="Assigned",
            availability_status=Tool.AvailabilityStatus.ASSIGNED,
        )
        Tool.objects.create(
            tool_id="D-T3",
            name="Damaged",
            availability_status=Tool.AvailabilityStatus.DAMAGED,
        )
        PPE.objects.create(ppe_id="D-P1", ppe_type="HELMET", name="Helmet")
        expired = PPE.objects.create(
            ppe_id="D-P2",
            ppe_type="GLOVES",
            name="Old Gloves",
            expiry_date="2020-01-01",
        )
        del expired
        assignment = PPEAssignment.objects.create(
            ppe=PPE.objects.get(ppe_id="D-P1"),
            worker=self.worker,
            issue_date="2026-08-01",
            issue_condition=PPE.Condition.GOOD,
        )
        del assignment
        Vehicle.objects.create(
            vehicle_id="D-V1",
            registration_number="JH01AA0001",
            vehicle_type="TRUCK",
            status=Vehicle.Status.AVAILABLE,
        )
        Vehicle.objects.create(
            vehicle_id="D-V2",
            registration_number="JH01AA0002",
            vehicle_type="VAN",
            status=Vehicle.Status.IN_USE,
        )

    def test_dashboard_counts_match_database(self):
        response = self.admin_client.get("/api/v1/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data["workers"]["total"], 3)  # worker1 + worker2 + inactive
        self.assertEqual(data["workers"]["active"], 2)
        self.assertEqual(data["projects"]["active"], 1)
        self.assertEqual(data["tools"]["available"], 1)
        self.assertEqual(data["tools"]["assigned"], 1)
        self.assertEqual(data["tools"]["attention"], 1)
        self.assertEqual(data["ppe"]["issued"], 1)
        self.assertEqual(data["ppe"]["attention"], 1)  # expired gloves
        self.assertEqual(data["vehicles"]["available"], 1)
        self.assertEqual(data["vehicles"]["in_use"], 1)

    def test_dashboard_forbidden_for_worker(self):
        response = self.worker_client.get("/api/v1/dashboard/")
        self.assertEqual(response.status_code, 403)


class AuditTrailTests(BaseAPITestCase):
    def test_audit_list_and_filter(self):
        from datetime import date

        tool = Tool.objects.create(tool_id="A-T1", name="Audit Tool")
        ToolAssignment.objects.create(
            tool=tool,
            worker=self.worker,
            issue_date=date.today(),
            issue_condition=Tool.Condition.GOOD,
        )
        ToolAssignment.objects.filter(pk=ToolAssignment.objects.latest("id").pk).update(
            status=ToolAssignment.Status.RETURNED, return_date=date.today()
        )
        # create audit rows manually to simulate full lifecycle records
        from apps.audit.services import record_audit

        record_audit(action="TOOL_ISSUED", entity=tool, actor=self.admin)
        record_audit(action="TOOL_RETURNED", entity=tool, actor=self.admin)

        response = self.admin_client.get("/api/v1/audit/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 2)

        filtered = self.admin_client.get("/api/v1/audit/", {"action": "TOOL_RETURNED"})
        self.assertGreaterEqual(filtered.data["count"], 1)
        for row in filtered.data["results"]:
            self.assertEqual(row["action"], "TOOL_RETURNED")

    def test_worker_cannot_read_audit_log(self):
        response = self.worker_client.get("/api/v1/audit/")
        self.assertEqual(response.status_code, 403)
