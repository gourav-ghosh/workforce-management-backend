"""Tests for the public host middleware (URL rewriting for media)."""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from apps.tools.models import Tool
from tests.utils import BaseAPITestCase


def _png_bytes():
    buf = BytesIO()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


@override_settings(
    PUBLIC_BASE_URL="https://api.example.com",
    ALLOWED_HOSTS=["*"],
)
class PublicHostMiddlewareTests(BaseAPITestCase):
    def test_rewrites_host_and_secure(self):
        from django.test import RequestFactory

        from apps.common.middleware import PublicHostMiddleware

        rf = RequestFactory()
        mw = PublicHostMiddleware(lambda r: r)
        request = rf.get("/api/v1/tools/")
        mw(request)
        # The request is a real ``WSGIRequest`` so ``wsgi.url_scheme`` is read
        # from ``request.META`` (which is the WSGI environ).
        self.assertEqual(request.META.get("HTTP_HOST"), "api.example.com")
        self.assertEqual(request.META.get("wsgi.url_scheme"), "https")
        self.assertEqual(request.get_host(), "api.example.com")
        self.assertEqual(request.scheme, "https")
        self.assertEqual(
            request.build_absolute_uri("/media/x.png"),
            "https://api.example.com/media/x.png",
        )

    def test_media_url_uses_public_base(self):
        from apps.tools.services import issue_tool

        tool = Tool.objects.create(tool_id="T-MED-1", name="Media URL test")
        issue_tool(
            actor=self.admin,
            tool_id=tool.pk,
            worker_id=self.worker.pk,
            media_files=[
                SimpleUploadedFile("p.png", _png_bytes(), content_type="image/png")
            ],
        )

        from apps.tools.models import ToolAssignment as TA

        assignment = TA.objects.get(tool=tool, worker=self.worker)
        response = self.worker_client.get(f"/api/v1/me/tools/{assignment.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertGreater(len(response.data["media"]), 0)
        media_url = response.data["media"][0]["file_url"]
        self.assertTrue(
            media_url.startswith("https://api.example.com/media/"),
            media_url,
        )
