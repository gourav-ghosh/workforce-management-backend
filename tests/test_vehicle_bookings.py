"""Tests for the new vehicle booking model + endpoint."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.transportation.models import Vehicle, VehicleBooking, VehicleBookingStatus
from apps.workers.models import WorkerProfile


class VehicleBookingTests(TestCase):
    def setUp(self):
        self.admin, _ = User.objects.get_or_create(
            mobile_number="+91 99000 88001",
            defaults=dict(role="ADMIN", is_staff=True, is_superuser=True),
        )
        self.admin.set_password("Admin@123")
        self.admin.save()
        self.worker_u, _ = User.objects.get_or_create(
            mobile_number="+91 99000 88002",
            defaults=dict(role="WORKER"),
        )
        self.worker_u.set_password("Work@123")
        self.worker_u.save()
        self.worker, _ = WorkerProfile.objects.get_or_create(
            user=self.worker_u,
            defaults=dict(
                employee_id="E_BK", full_name="Booking Tester",
                phone_number="+91 99000 88002", employment_status="ACTIVE",
            ),
        )
        self.vehicle, _ = Vehicle.objects.get_or_create(
            vehicle_id="VEH-BK",
            defaults=dict(
                registration_number="JH05BK1234",
                vehicle_type=Vehicle.VehicleType.TRUCK,
                status=Vehicle.Status.AVAILABLE,
            ),
        )

    def test_create_list_get_update_delete_booking(self):
        api = APIClient()
        api.force_authenticate(user=self.admin)

        start = timezone.now() + timedelta(days=1)
        end = start + timedelta(hours=4)

        # Create
        resp = api.post(
            f"/api/v1/vehicles/{self.vehicle.pk}/bookings/",
            data={
                "booking_type": "PROJECT",
                "start_datetime": start.isoformat(),
                "end_datetime": end.isoformat(),
                "worker": self.worker.pk,
                "purpose": "Project site transport",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        booking_id = resp.json()["id"]
        self.assertEqual(resp.json()["status"], VehicleBookingStatus.SCHEDULED)
        self.assertEqual(resp.json()["purpose"], "Project site transport")

        # List
        resp2 = api.get(f"/api/v1/vehicles/{self.vehicle.pk}/bookings/")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(len(resp2.json()), 1)

        # Calendar view
        resp3 = api.get("/api/v1/vehicles/bookings/")
        self.assertEqual(resp3.status_code, 200)

        # Get
        resp4 = api.get(f"/api/v1/vehicles/{self.vehicle.pk}/bookings/{booking_id}/")
        self.assertEqual(resp4.status_code, 200)
        self.assertEqual(resp4.json()["worker_name"], "Booking Tester")

        # Update
        resp5 = api.put(
            f"/api/v1/vehicles/{self.vehicle.pk}/bookings/{booking_id}/",
            data={"status": "CONFIRMED", "purpose": "Updated"},
            format="json",
        )
        self.assertEqual(resp5.status_code, 200, resp5.content)
        self.assertEqual(resp5.json()["status"], "CONFIRMED")

        # Overlap check
        resp6 = api.post(
            f"/api/v1/vehicles/{self.vehicle.pk}/bookings/",
            data={
                "booking_type": "PROJECT",
                "start_datetime": (start + timedelta(minutes=30)).isoformat(),
                "end_datetime": (end + timedelta(minutes=30)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp6.status_code, 409, resp6.content)
        self.assertEqual(resp6.json()["code"], "BOOKING_OVERLAP")

        # Delete
        resp7 = api.delete(
            f"/api/v1/vehicles/{self.vehicle.pk}/bookings/{booking_id}/"
        )
        self.assertEqual(resp7.status_code, 204)

    def test_vehicle_routes_accept_business_code(self):
        api = APIClient()
        api.force_authenticate(user=self.admin)

        detail = api.get(f"/api/v1/vehicles/{self.vehicle.vehicle_id}/")
        self.assertEqual(detail.status_code, 200, detail.content)

        bookings = api.get(f"/api/v1/vehicles/{self.vehicle.vehicle_id}/bookings/")
        self.assertEqual(bookings.status_code, 200, bookings.content)

    def test_missing_vehicle_returns_404(self):
        api = APIClient()
        api.force_authenticate(user=self.admin)

        response = api.get("/api/v1/vehicles/VEH-DOES-NOT-EXIST/")
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.json()["code"], "VEHICLE_NOT_FOUND")

    def test_past_booking_is_rejected(self):
        api = APIClient()
        api.force_authenticate(user=self.admin)
        start = timezone.now() - timedelta(hours=1)

        response = api.post(
            f"/api/v1/vehicles/{self.vehicle.vehicle_id}/bookings/",
            data={
                "booking_type": "GENERAL_USE",
                "start_datetime": start.isoformat(),
                "end_datetime": (start + timedelta(hours=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("start_datetime", response.json())

    def test_fleet_booking_feed_is_upcoming_and_excludes_cancelled(self):
        now = timezone.now()
        VehicleBooking.objects.create(
            vehicle=self.vehicle,
            booking_type=VehicleBooking.BookingType.GENERAL_USE,
            start_datetime=now - timedelta(days=1),
            end_datetime=now - timedelta(hours=1),
            status=VehicleBookingStatus.SCHEDULED,
        )
        cancelled = VehicleBooking.objects.create(
            vehicle=self.vehicle,
            booking_type=VehicleBooking.BookingType.GENERAL_USE,
            start_datetime=now + timedelta(days=1),
            end_datetime=now + timedelta(days=2),
            status=VehicleBookingStatus.CANCELLED,
        )
        upcoming = VehicleBooking.objects.create(
            vehicle=self.vehicle,
            booking_type=VehicleBooking.BookingType.GENERAL_USE,
            start_datetime=now + timedelta(days=2),
            end_datetime=now + timedelta(days=3),
            status=VehicleBookingStatus.SCHEDULED,
        )

        api = APIClient()
        api.force_authenticate(user=self.admin)
        response = api.get("/api/v1/vehicles/bookings/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([item["id"] for item in response.json()], [upcoming.pk])
        self.assertNotIn(cancelled.pk, [item["id"] for item in response.json()])

    def test_vehicle_type_includes_trailer_and_dumper(self):
        self.assertIn("TRAILER", dict(Vehicle.VehicleType.choices))
        self.assertIn("DUMPER", dict(Vehicle.VehicleType.choices))

    def test_vehicle_stocks_endpoint(self):
        api = APIClient()
        api.force_authenticate(user=self.admin)
        resp = api.get("/api/v1/vehicles/stock/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total"], 1)
        self.assertEqual(resp.json()["available"], 1)

    def test_ppe_stocks_endpoint(self):
        from apps.ppe.models import PPE
        PPE.objects.get_or_create(
            ppe_id="PPE-BK-1",
            defaults=dict(
                ppe_type=PPE.PPEType.HELMET,
                name="Test Helmet",
                category="Head protection",
                size="Free",
                condition=PPE.Condition.GOOD,
                availability_status=PPE.AvailabilityStatus.AVAILABLE,
            ),
        )
        api = APIClient()
        api.force_authenticate(user=self.admin)
        resp = api.get("/api/v1/ppe/stock/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total"], 1)
        self.assertEqual(resp.json()["available"], 1)

    def test_vehicle_stock_counts_endpoint(self):
        Vehicle.objects.create(
            vehicle_id="VEH-STK-A",
            registration_number="JH05STK1234",
            vehicle_type=Vehicle.VehicleType.TRUCK,
            status=Vehicle.Status.AVAILABLE,
        )
        Vehicle.objects.create(
            vehicle_id="VEH-STK-B",
            registration_number="JH05STK5678",
            vehicle_type=Vehicle.VehicleType.DUMPER,
            status=Vehicle.Status.AVAILABLE,
        )
        api = APIClient()
        api.force_authenticate(user=self.admin)
        resp = api.get("/api/v1/vehicles/stock/")
        self.assertEqual(resp.status_code, 200)
        # Just verify the new types are present in the response.
        body = resp.json()
        self.assertIn("truck", body)
        self.assertIn("dumper", body)
        self.assertGreaterEqual(body["truck"], 1)
        self.assertGreaterEqual(body["dumper"], 1)
