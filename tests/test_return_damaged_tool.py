"""Tests that returning a damaged tool succeeds end-to-end."""
import io
import json

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.tools.models import Tool, ToolAssignment, ToolDamage
from apps.workers.models import WorkerProfile
from datetime import date
from PIL import Image as PilImage


class ReturnDamagedToolTests(TestCase):
    def setUp(self):
        self.admin, _ = User.objects.get_or_create(
            mobile_number="+91 99999 01001",
            defaults=dict(role="ADMIN", is_staff=True, is_superuser=True),
        )
        self.admin.set_password("Admin@123"); self.admin.save()
        self.worker_u, _ = User.objects.get_or_create(
            mobile_number="+91 99999 01002",
            defaults=dict(role="WORKER"),
        )
        self.worker_u.set_password("Work@123"); self.worker_u.save()
        self.worker, _ = WorkerProfile.objects.get_or_create(
            user=self.worker_u,
            defaults=dict(
                employee_id="E_RD", full_name="RD Tester",
                phone_number="+91 99999 01002", employment_status="ACTIVE",
            ),
        )
        self.tool, _ = Tool.objects.get_or_create(
            tool_id="T_RD",
            defaults=dict(name="Repaired Tool", category="Power Tools"),
        )
        ToolAssignment.objects.filter(
            tool=self.tool, status="ACTIVE"
        ).update(
            status="RETURNED", return_date=date.today(), return_condition="GOOD",
        )
        self.assignment = ToolAssignment.objects.create(
            tool=self.tool, worker=self.worker,
            issue_date=date.today(), issue_condition="GOOD",
        )

    def _png(self, color=(255, 0, 0)):
        buf = io.BytesIO()
        PilImage.new("RGB", (100, 100), color).save(buf, format="PNG")
        return buf.getvalue()

    def test_admin_returns_damaged_tool(self):
        # 1) Admin records a damage while the tool is assigned.
        api = APIClient()
        api.force_authenticate(user=self.admin)
        from django.core.files.uploadedfile import SimpleUploadedFile
        damage_resp = api.post(
            f"/api/v1/tools/{self.tool.pk}/damage/",
            data={
                "assignment_id": self.assignment.pk,
                "damage_description": "Cracked handle",
                "damage_condition": "DAMAGED",
                "photos": SimpleUploadedFile("d.png", self._png(), "image/png"),
            },
            format="multipart",
        )
        self.assertEqual(damage_resp.status_code, 201, damage_resp.content)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.availability_status, Tool.AvailabilityStatus.DAMAGED)

        # 2) Admin returns the tool as DAMAGED.
        ret = api.post(
            f"/api/v1/tools/{self.tool.pk}/return/",
            data={
                "return_condition": "DAMAGED",
                "return_date": date.today().isoformat(),
                "remarks": "Returned for repair",
                "photos": SimpleUploadedFile("r.png", self._png(color=(0, 0, 255)), "image/png"),
            },
            format="multipart",
        )
        self.assertEqual(ret.status_code, 200, ret.content)
        body = ret.json()
        self.assertEqual(body["status"], "RETURNED")
        self.assertEqual(body["return_condition"], "DAMAGED")

        # Tool is now DAMAGED with the new photo + closed assignment.
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.availability_status, Tool.AvailabilityStatus.DAMAGED)
        self.assertEqual(self.tool.condition, "DAMAGED")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "RETURNED")
        self.assertEqual(self.assignment.return_condition, "DAMAGED")

        # 3) Return photos are linked to the assignment.
        self.assertGreaterEqual(self.tool.media.count(), 2)
