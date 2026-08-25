"""Vehicle CRUD + assign/unassign/history workflow tests."""

from datetime import timedelta

from django.utils import timezone

from apps.audit.models import AuditLog
from apps.transportation.models import Vehicle, VehicleAssignment
from tests.utils import BaseAPITestCase

VEHICLES_URL = "/api/v1/vehicles/"


class VehicleCrudTests(BaseAPITestCase):
    def test_create_vehicle(self):
        response = self.admin_client.post(
            VEHICLES_URL,
            {
                "vehicle_id": "VEH-900",
                "registration_number": "jh05zz9999",
                "vehicle_type": "TRUCK",
                "make_model": "Tata 407",
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        vehicle = Vehicle.objects.get(vehicle_id="VEH-900")
        # Registration numbers normalised to upper case.
        self.assertEqual(vehicle.registration_number, "JH05ZZ9999")

    def test_duplicate_registration_rejected(self):
        payload = {
            "vehicle_id": "VEH-901",
            "registration_number": "JH05AA1111",
            "vehicle_type": "VAN",
        }
        self.admin_client.post(VEHICLES_URL, payload)
        dup = self.admin_client.post(VEHICLES_URL, {**payload, "vehicle_id": "VEH-902"})
        self.assertEqual(dup.status_code, 400)

    def test_delete_blocked_with_history(self):
        vehicle = Vehicle.objects.create(
            vehicle_id="VEH-903",
            registration_number="JH05BB2222",
            vehicle_type="CAR",
        )
        VehicleAssignment.objects.create(
            vehicle=vehicle,
            assignment_type=VehicleAssignment.AssignmentType.GENERAL_USE,
            start_datetime=timezone.now() - timedelta(days=1),
        )
        response = self.admin_client.delete(f"{VEHICLES_URL}{vehicle.pk}/")
        self.assertEqual(response.status_code, 409)


class VehicleAssignmentTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.vehicle = Vehicle.objects.create(
            vehicle_id="VEH-910",
            registration_number="JH05CC3333",
            vehicle_type="PICKUP",
        )

    def assign(self, **overrides):
        start = timezone.now()
        payload = {
            "assignment_type": VehicleAssignment.AssignmentType.PROJECT,
            "start_datetime": (start - timedelta(days=1)).isoformat(),
            "purpose": "Site material runs",
        }
        payload.update(overrides)
        return self.admin_client.post(f"{VEHICLES_URL}{self.vehicle.pk}/assign/", payload)

    def test_assign_marks_in_use_and_audits(self):
        response = self.assign()
        self.assertEqual(response.status_code, 201, response.data)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.IN_USE)
        self.assertTrue(AuditLog.objects.filter(action="VEHICLE_ASSIGNED").exists())

    def test_unassign_restores_available(self):
        self.assign()
        response = self.admin_client.post(f"{VEHICLES_URL}{self.vehicle.pk}/unassign/", {})
        self.assertEqual(response.status_code, 200)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.AVAILABLE)

    def test_open_ended_assignment_blocks_new_overlap(self):
        self.assign(end_datetime=None)
        conflict = self.assign(purpose="Second run")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["code"], "VEHICLE_OVERLAP")

    def test_overlapping_bounded_ranges_conflict(self):
        now = timezone.now()
        self.assign(
            start_datetime=(now + timedelta(days=2)).isoformat(),
            end_datetime=(now + timedelta(days=5)).isoformat(),
        )
        overlap = self.assign(
            start_datetime=(now + timedelta(days=4)).isoformat(),
            end_datetime=(now + timedelta(days=6)).isoformat(),
        )
        self.assertEqual(overlap.status_code, 409)

    def test_sequential_bounded_assignments_allowed(self):
        now = timezone.now()
        first = self.assign(
            start_datetime=now.isoformat(),
            end_datetime=(now + timedelta(days=2)).isoformat(),
        )
        second = self.assign(
            start_datetime=(now + timedelta(days=3)).isoformat(),
            end_datetime=(now + timedelta(days=5)).isoformat(),
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

    def test_context_rule_requires_project_worker_or_purpose(self):
        start = timezone.now().isoformat()
        response = self.admin_client.post(
            f"{VEHICLES_URL}{self.vehicle.pk}/assign/",
            {"assignment_type": "OTHER", "start_datetime": start},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "MISSING_ASSIGNMENT_CONTEXT")

    def test_end_before_start_rejected(self):
        now = timezone.now()
        response = self.assign(
            start_datetime=(now + timedelta(days=5)).isoformat(),
            end_datetime=(now + timedelta(days=1)).isoformat(),
            purpose="Backwards range",
        )
        self.assertEqual(response.status_code, 409)

    def test_history_lists_all_assignments(self):
        now = timezone.now()
        self.assign(
            start_datetime=(now - timedelta(days=10)).isoformat(),
            end_datetime=(now - timedelta(days=5)).isoformat(),
        )
        self.assign(start_datetime=now.isoformat())
        history = self.admin_client.get(f"{VEHICLES_URL}{self.vehicle.pk}/history/")
        self.assertEqual(history.data["count"], 2)

    def test_worker_sees_own_transportation(self):
        self.assign(
            worker_id=self.worker.pk,
            assignment_type=VehicleAssignment.AssignmentType.WORKER_TRANSPORT,
            purpose="Crew transport",
        )
        response = self.worker_client.get("/api/v1/me/vehicles/")
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("role", results[0])
