"""Image upload validation and safe-filename tests."""

from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.tools.models import Tool
from tests.utils import BaseAPITestCase, make_image_file, make_png_bytes

TOOLS_URL = "/api/v1/tools/"


def fake_text_file(name="notes.txt"):
    return SimpleUploadedFile(name, b"not an image", content_type="text/plain")


class ImageUploadTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.tool = Tool.objects.create(tool_id="T-MEDIA-1", name="Camera Drill")

    def test_tool_photo_upload_generates_safe_filename(self):
        upload = make_image_file(name="../../evil name ().png")
        response = self.admin_client.post(
            TOOLS_URL,
            {"tool_id": "T-MEDIA-2", "name": "Photo Tool", "photo": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        from apps.tools.models import Tool as T

        tool = T.objects.get(tool_id="T-MEDIA-2")
        self.assertIn("tools/photos/", tool.photo.name)
        self.assertTrue(tool.photo.name.endswith(".png"))
        # The client-supplied filename must not appear in the stored path.
        self.assertNotIn("evil", tool.photo.name)

    def test_media_endpoint_accepts_png(self):
        upload = make_image_file(name="condition.png")
        response = self.admin_client.post(
            f"{TOOLS_URL}{self.tool.pk}/media/",
            {"file": upload, "media_type": "ISSUE"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("file_url", response.data)

    def test_non_image_rejected(self):
        upload = fake_text_file()
        response = self.admin_client.post(
            f"{TOOLS_URL}{self.tool.pk}/media/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_corrupted_image_rejected(self):
        upload = SimpleUploadedFile("fake.png", b"\x89PNG not really", content_type="image/png")
        response = self.admin_client.post(
            f"{TOOLS_URL}{self.tool.pk}/media/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(
        DATA_UPLOAD_MAX_MEMORY_SIZE=1024 * 500, FILE_UPLOAD_MAX_MEMORY_SIZE=1024 * 500
    )
    def test_oversized_image_rejected(self):
        with mock.patch("django.conf.settings.MAX_UPLOAD_SIZE_MB", 0) as _:
            big = SimpleUploadedFile(
                "big.png", make_png_bytes((2000, 2000)), content_type="image/png"
            )
            response = self.admin_client.post(
                f"{TOOLS_URL}{self.tool.pk}/media/",
                {"file": big},
                format="multipart",
            )
        self.assertEqual(response.status_code, 400)

    def test_issue_with_photos_stores_return_media(self):
        create = self.admin_client.post(
            TOOLS_URL, {"tool_id": "T-MEDIA-3", "name": "Return Photo Tool"}
        )
        tool_id = create.data["id"]
        self.admin_client.post(f"{TOOLS_URL}{tool_id}/assign/", {"worker_id": self.worker.pk})
        photo = make_image_file(name="return-condition.png")
        response = self.admin_client.post(
            f"{TOOLS_URL}{tool_id}/return/",
            {"return_condition": "GOOD", "photos": photo},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        from apps.tools.models import ToolMedia

        media = ToolMedia.objects.filter(tool_id=tool_id, media_type="RETURN")
        self.assertEqual(media.count(), 1)
