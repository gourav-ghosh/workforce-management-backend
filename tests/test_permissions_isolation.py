"""Role permissions and worker data isolation tests.

The backend is the authoritative permission layer: the mobile app hiding a
screen must never be the only protection.
"""

from rest_framework.test import APIClient

from tests.utils import BaseAPITestCase

ADMIN_ONLY_LIST_ENDPOINTS = [
    "/api/v1/workers/",
    "/api/v1/projects/",
    "/api/v1/tools/",
    "/api/v1/ppe/",
    "/api/v1/vehicles/",
    "/api/v1/audit/",
    "/api/v1/dashboard/",
]


class RolePermissionTests(BaseAPITestCase):
    def test_worker_cannot_access_admin_list_endpoints(self):
        for url in ADMIN_ONLY_LIST_ENDPOINTS:
            with self.subTest(url=url):
                response = self.worker_client.get(url)
                self.assertEqual(response.status_code, 403, url)

    def test_worker_cannot_create_or_modify_admin_resources(self):
        response = self.worker_client.post(
            "/api/v1/tools/",
            {
                "tool_id": "T-999",
                "name": "Sneaky Tool",
            },
        )
        self.assertEqual(response.status_code, 403)

        response = self.other_client.get(f"/api/v1/workers/{self.worker.pk}/")
        self.assertIn(response.status_code, (403, 404))

    def test_anonymous_cannot_access_anything(self):
        anon = APIClient()
        for url in ["/api/v1/me/", *ADMIN_ONLY_LIST_ENDPOINTS]:
            with self.subTest(url=url):
                self.assertEqual(anon.get(url).status_code, 401)


class WorkerDataIsolationTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        from apps.projects.models import Project, ProjectWorker
        from apps.tools.models import Tool, ToolAssignment

        self.project = Project.objects.create(
            project_number="PRJ-ISO-1",
            project_name="Isolation Project",
            status=Project.Status.ACTIVE,
        )
        ProjectWorker.objects.get_or_create(
            project=self.project, worker=self.worker, defaults={"is_active": True}
        )

        self.tool = Tool.objects.create(
            tool_id="T-ISO-1",
            name="Isolated Drill",
            availability_status=Tool.AvailabilityStatus.ASSIGNED,
        )
        self.assignment = ToolAssignment.objects.create(
            tool=self.tool,
            worker=self.worker,
            issue_date="2026-08-01",
            issue_condition=Tool.Condition.GOOD,
        )

    def test_worker_sees_own_projects_via_me(self):
        response = self.worker_client.get("/api/v1/me/projects/")
        self.assertEqual(response.status_code, 200)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["project"]["project_number"], "PRJ-ISO-1")

    def test_worker_does_not_see_other_workers_projects(self):
        response = self.other_client.get("/api/v1/me/projects/")
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 0)

    def test_worker_tools_scoped_to_owner(self):
        mine = self.worker_client.get("/api/v1/me/tools/")
        theirs = self.other_client.get("/api/v1/me/tools/")
        mine_results = mine.data["results"] if isinstance(mine.data, dict) else mine.data
        their_results = theirs.data["results"] if isinstance(theirs.data, dict) else theirs.data
        self.assertEqual(len(mine_results), 1)
        self.assertEqual(len(their_results), 0)

    def test_worker_cannot_fetch_other_worker_profile_record(self):
        # /workers/{id} is admin-only; a worker cannot read another profile by ID.
        response = self.other_client.get(f"/api/v1/workers/{self.worker.pk}/")
        self.assertEqual(response.status_code, 403)

    def test_worker_cannot_mutate_assignments(self):
        response = self.worker_client.post(
            f"/api/v1/tools/{self.tool.pk}/assign/",
            {"worker_id": self.worker.pk},
        )
        self.assertEqual(response.status_code, 403)

    def test_worker_summary_counts_only_owned(self):
        mine = self.worker_client.get("/api/v1/me/summary/")
        theirs = self.other_client.get("/api/v1/me/summary/")
        self.assertEqual(mine.data["tools"], 1)
        self.assertEqual(theirs.data["tools"], 0)
