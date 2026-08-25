"""Shared test helpers."""

import io

from django.contrib.auth import get_user_model
from PIL import Image
from rest_framework.test import APIClient
from rest_framework.test import APITestCase as DRFAPITestCase

User = get_user_model()

ADMIN_PASSWORD = "AdminPass@123"
WORKER_PASSWORD = "WorkerPass@123"


def make_png_bytes(size=(8, 8), color=(255, 0, 0)):
    buffer = io.BytesIO()
    image = Image.new("RGB", size, color)
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


def make_image_file(name="photo.png"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, make_png_bytes(), content_type="image/png")


class BaseAPITestCase(DRFAPITestCase):
    def setUp(self):
        self.admin = self.make_admin()
        self.worker = self.make_worker(username="worker1", employee_id="EMP001")
        self.other_worker = self.make_worker(
            username="worker2", employee_id="EMP002", full_name="Second Worker"
        )
        self.admin_client = self.client_for(self.admin)
        self.worker_client = self.client_for(self.worker.user)
        self.other_client = self.client_for(self.other_worker.user)

    @staticmethod
    def make_admin(username="admin1"):
        user = User.objects.create_user(
            username=username, password=ADMIN_PASSWORD, role=User.Role.ADMIN
        )
        return user

    @staticmethod
    def make_worker(
        username,
        employee_id,
        full_name="Test Worker",
        active=True,
        employment_status=None,
    ):
        from apps.workers.models import WorkerProfile

        user = User.objects.create_user(
            username=username,
            password=WORKER_PASSWORD,
            role=User.Role.WORKER,
            is_active=active,
        )
        if employment_status is None:
            employment_status = (
                WorkerProfile.EmploymentStatus.ACTIVE
                if active
                else WorkerProfile.EmploymentStatus.INACTIVE
            )
        return WorkerProfile.objects.create(
            user=user,
            employee_id=employee_id,
            full_name=full_name,
            phone_number="+91 90000 00000",
            employment_status=employment_status,
        )

    @staticmethod
    def client_for(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client
