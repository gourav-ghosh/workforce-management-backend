"""Worker-scoped project detail endpoint tests."""

from apps.projects.models import Project, ProjectWorker
from tests.utils import BaseAPITestCase


class MyProjectDetailTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            project_number="PRJ-DET-1",
            project_name="Worker-visible project",
            client_name="Acme",
            location="Ranchi",
        )
        ProjectWorker.objects.create(
            project=self.project, worker=self.worker, is_active=True
        )
        self.other_project = Project.objects.create(
            project_number="PRJ-DET-2",
            project_name="Hidden project",
            client_name="Hidden",
            location="Hidden",
        )

    def test_assigned_worker_can_read_project_detail(self):
        response = self.worker_client.get(f"/api/v1/me/projects/{self.project.pk}/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["project_name"], "Worker-visible project")

    def test_unassigned_worker_is_blocked(self):
        response = self.worker_client.get(f"/api/v1/me/projects/{self.other_project.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "PROJECT_NOT_ASSIGNED")

    def test_admin_uses_admin_endpoint(self):
        response = self.admin_client.get(f"/api/v1/projects/{self.project.pk}/")
        self.assertEqual(response.status_code, 200)
