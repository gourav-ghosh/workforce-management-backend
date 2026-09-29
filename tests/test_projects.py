"""Project CRUD and worker assignment workflow tests."""

from apps.projects.models import Project, ProjectWorker
from tests.utils import BaseAPITestCase, make_image_file

PROJECTS_URL = "/api/v1/projects/"


def project_payload(**overrides):
    data = {
        "project_number": "PRJ-TEST-1",
        "project_name": "Test Project",
        "client_name": "Acme Corp",
        "location": "Ranchi",
        "description": "A test project",
        "start_date": "2026-08-01",
        "expected_completion_date": "2026-12-31",
        "permit_no": "P-100",
        "total_manpower": 10,
        "job": "Wiring",
        "measurement_sheet_status": "NOT_SUBMITTED",
        "status": "PLANNED",
        "notes": "",
    }
    data.update(overrides)
    return data


class ProjectCrudTests(BaseAPITestCase):
    def test_create_project_minimal(self):
        response = self.admin_client.post(
            PROJECTS_URL, {"project_number": "PRJ-9", "project_name": "Minimal"}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(Project.objects.first().status, Project.Status.DRAFT)

    def test_create_requires_number_and_name(self):
        response = self.admin_client.post(PROJECTS_URL, {"client_name": "No number"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("project_number", response.data)

    def test_completion_date_must_follow_start_date(self):
        response = self.admin_client.post(
            PROJECTS_URL,
            project_payload(start_date="2026-09-01", expected_completion_date="2026-08-01"),
        )
        self.assertEqual(response.status_code, 400)

    def test_duplicate_project_number_rejected(self):
        self.admin_client.post(PROJECTS_URL, project_payload())
        dup = self.admin_client.post(PROJECTS_URL, project_payload(project_name="Dup"))
        self.assertEqual(dup.status_code, 400)

    def test_update_project_fields(self):
        create = self.admin_client.post(PROJECTS_URL, project_payload())
        project_id = create.data["id"]
        patch = self.admin_client.patch(f"{PROJECTS_URL}{project_id}/", {"status": "ACTIVE"})
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.data["status"], "ACTIVE")

    def test_requirement_fields_default_to_blank(self):
        response = self.admin_client.post(
            PROJECTS_URL,
            {"project_number": "PRJ-BLANK", "project_name": "No extras"},
        )
        self.assertEqual(response.status_code, 201, response.data)
        project = Project.objects.get(pk=response.data["id"])
        self.assertEqual(project.material_required, "")
        self.assertEqual(project.ppe_required, "")
        self.assertEqual(project.measurement_after_bill_status, "")

    def test_requirement_fields_are_optional_and_saved(self):
        response = self.admin_client.post(
            PROJECTS_URL,
            project_payload(
                material_required="Cement 50 bags\nSteel 2 tons",
                ppe_required="Helmet, safety shoes, gloves",
                measurement_after_bill_status="Pending client approval",
            ),
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["material_required"], "Cement 50 bags\nSteel 2 tons")
        self.assertEqual(response.data["ppe_required"], "Helmet, safety shoes, gloves")
        self.assertEqual(response.data["measurement_after_bill_status"], "Pending client approval")
        detail = self.admin_client.get(f"{PROJECTS_URL}{response.data['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["material_required"], "Cement 50 bags\nSteel 2 tons")
        self.assertEqual(detail.data["measurement_after_bill_status"], "Pending client approval")

    def test_requirement_fields_can_be_cleared(self):
        created = self.admin_client.post(
            PROJECTS_URL,
            project_payload(material_required="Cement", ppe_required="Helmet"),
        )
        self.assertEqual(created.status_code, 201, created.data)
        patch = self.admin_client.patch(
            f"{PROJECTS_URL}{created.data['id']}/",
            {"material_required": "", "ppe_required": ""},
        )
        self.assertEqual(patch.status_code, 200, patch.data)
        self.assertEqual(patch.data["material_required"], "")
        self.assertEqual(patch.data["ppe_required"], "")

    def test_patch_omitting_requirement_fields_keeps_them(self):
        created = self.admin_client.post(PROJECTS_URL, project_payload(ppe_required="Helmet"))
        self.assertEqual(created.status_code, 201, created.data)
        patch = self.admin_client.patch(
            f"{PROJECTS_URL}{created.data['id']}/", {"status": "ACTIVE"}
        )
        self.assertEqual(patch.status_code, 200, patch.data)
        self.assertEqual(patch.data["ppe_required"], "Helmet")

    def test_list_omits_requirement_fields(self):
        """The list payload stays lean; the fields are detail-only."""
        self.admin_client.post(PROJECTS_URL, project_payload(material_required="Cement"))
        response = self.admin_client.get(PROJECTS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("material_required", response.data["results"][0])
        self.assertNotIn("ppe_required", response.data["results"][0])
        self.assertNotIn("measurement_after_bill_status", response.data["results"][0])

    def test_delete_blocked_with_assignments(self):
        create = self.admin_client.post(PROJECTS_URL, project_payload())
        project_id = create.data["id"]
        ProjectWorker.objects.create(project_id=project_id, worker=self.worker)
        response = self.admin_client.delete(f"{PROJECTS_URL}{project_id}/")
        self.assertEqual(response.status_code, 409)

    def test_plan_document_upload(self):
        plan = make_image_file(name="plan.png")
        response = self.admin_client.post(
            PROJECTS_URL,
            {**project_payload(), "project_plan": plan},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)


class ProjectWorkerAssignmentTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            project_number="PRJ-WF-1", project_name="Workflow Project"
        )

    def assign(self, worker_id):
        return self.admin_client.post(
            f"{PROJECTS_URL}{self.project.pk}/workers/", {"worker_id": worker_id}
        )

    def test_assign_and_unassign_flow(self):
        response = self.assign(self.worker.pk)
        self.assertEqual(response.status_code, 201, response.data)
        assignment = ProjectWorker.objects.get(pk=response.data["id"])
        self.assertTrue(assignment.is_active)

        remove = self.admin_client.delete(
            f"{PROJECTS_URL}{self.project.pk}/workers/{self.worker.pk}/"
        )
        self.assertEqual(remove.status_code, 204)
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertIsNotNone(assignment.unassigned_at)

    def test_history_preserved_on_reassignment(self):
        first = self.assign(self.worker.pk)
        self.admin_client.delete(f"{PROJECTS_URL}{self.project.pk}/workers/{self.worker.pk}/")
        second = self.assign(self.worker.pk)
        self.assertEqual(second.status_code, 201)
        rows = ProjectWorker.objects.filter(project=self.project, worker=self.worker)
        self.assertEqual(rows.count(), 2)
        self.assertNotEqual(first.data["id"], second.data["id"])

    def test_double_assignment_conflicts(self):
        self.assign(self.worker.pk)
        again = self.assign(self.worker.pk)
        self.assertEqual(again.status_code, 409)

    def test_assign_unknown_worker_rejected(self):
        response = self.assign(99999)
        self.assertIn(response.status_code, (400, 409))

    def test_listing_assignments(self):
        self.assign(self.worker.pk)
        response = self.admin_client.get(f"{PROJECTS_URL}{self.project.pk}/workers/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 1)

    def test_audit_record_created_for_assignment(self):
        from apps.audit.models import AuditLog

        self.assign(self.worker.pk)
        exists = AuditLog.objects.filter(
            action="WORKER_ASSIGNED_TO_PROJECT",
            entity_type="ProjectWorker",
            entity_id=str(ProjectWorker.objects.latest("id").pk),
        ).exists()
        self.assertTrue(exists)
