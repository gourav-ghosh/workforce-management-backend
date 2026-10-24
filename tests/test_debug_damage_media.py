"""Tests what URL the admin tool history endpoint returns for damage
photos so we can verify the admin sees them too.
"""
import io
import json
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image as PilImage
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.tools.models import Tool, ToolAssignment
from apps.workers.models import WorkerProfile


class DebugDamageMedia(TestCase):
    def test_admin_tool_history(self):
        admin, _ = User.objects.get_or_create(
            mobile_number="+91 90000 99999",
            defaults=dict(role="ADMIN", is_staff=True, is_superuser=True),
        )
        admin.set_password("Admin@123"); admin.save()
        worker_u, _ = User.objects.get_or_create(
            mobile_number="+91 90000 88888",
            defaults=dict(role="WORKER"),
        )
        worker_u.set_password("Work@123"); worker_u.save()
        worker, _ = WorkerProfile.objects.get_or_create(
            user=worker_u, defaults=dict(
                employee_id="E_DBG", full_name="DBG",
                phone_number="+91 90000 88888", employment_status="ACTIVE",
            ),
        )
        tool, _ = Tool.objects.get_or_create(
            tool_id="T_DBG", defaults=dict(name="Debug Tool", category="Power Tools"),
        )
        ToolAssignment.objects.filter(tool=tool, status="ACTIVE").update(
            status="RETURNED", return_date=date.today(), return_condition="GOOD",
        )
        assignment = ToolAssignment.objects.create(
            tool=tool, worker=worker, issue_date=date.today(), issue_condition="GOOD",
        )

        def png():
            buf = io.BytesIO()
            PilImage.new("RGB", (200, 200), (200, 50, 50)).save(buf, format="PNG")
            return buf.getvalue()

        # Admin creates damage linked to the worker's active assignment.
        api = APIClient()
        api.force_authenticate(user=admin)
        resp = api.post(
            f"/api/v1/tools/{tool.pk}/damage/",
            data={
                "assignment_id": assignment.pk,
                "damage_description": "Damage with photo",
                "damage_condition": "DAMAGED",
                "remarks": "x",
                "photos": SimpleUploadedFile("p.png", png(), "image/png"),
            },
            format="multipart",
        )
        print("CREATE STATUS:", resp.status_code)
        print("CREATE MEDIA:", json.dumps(resp.json().get("media"), indent=2))

        # Now check the admin tool history endpoint to see what damage is returned.
        resp2 = api.get(f"/api/v1/tools/{tool.pk}/history/")
        print("ADMIN HISTORY STATUS:", resp2.status_code)
        for item in resp2.json().get("results", []):
            print("  Assignment", item["id"], "damages:", item.get("damages"))

        # Now check the worker tool detail endpoint.
        api_w = APIClient()
        api_w.force_authenticate(user=worker_u)
        resp3 = api_w.get(f"/api/v1/me/tools/{assignment.pk}/")
        print("WORKER DETAIL STATUS:", resp3.status_code)
        body = resp3.json()
        print("WORKER DETAIL damages:", json.dumps(body.get("damages"), indent=2))
        print("WORKER DETAIL media:", json.dumps(body.get("media"), indent=2))

        # Also check the admin tool detail endpoint to see if it shows damage.
        resp4 = api.get(f"/api/v1/tools/{tool.pk}/")
        print("ADMIN DETAIL STATUS:", resp4.status_code)
        print("ADMIN DETAIL open_damage_count:", resp4.json().get("open_damage_count"))
