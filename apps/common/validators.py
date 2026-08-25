"""Upload validators and safe filename helpers."""

import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image

_ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
}


def _max_bytes():
    return settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


def validate_image_file(file_obj):
    """Validate an uploaded image by declared MIME type, size and decodability."""
    max_mb = settings.MAX_UPLOAD_SIZE_MB
    if file_obj.size > _max_bytes():
        raise ValidationError(f"File exceeds the maximum allowed size of {max_mb} MB.")

    content_type = getattr(file_obj, "content_type", "") or ""
    if content_type not in settings.ALLOWED_IMAGE_MIME_TYPES:
        raise ValidationError("Unsupported image format. Allowed formats: JPEG, PNG, WebP.")

    try:
        image = Image.open(file_obj)
        image.verify()
    except Exception:
        raise ValidationError("The uploaded file is not a valid image.")
    finally:
        file_obj.seek(0)


def validate_document_file(file_obj):
    """Validate a project plan/document upload by extension and size."""
    max_mb = settings.MAX_UPLOAD_SIZE_MB
    if file_obj.size > _max_bytes():
        raise ValidationError(f"File exceeds the maximum allowed size of {max_mb} MB.")
    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext not in _ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError("Unsupported document type.")


def generate_upload_path(prefix, filename):
    """Return a safe upload path under ``prefix/`` with a generated filename.

    Client-supplied filenames are never trusted; only the extension is kept
    (and only when it belongs to a known-safe whitelist).
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_IMAGE_EXTENSIONS:
        ext = ".jpg"
    return f"{prefix}/{uuid.uuid4().hex}{ext}"


def generate_document_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_DOCUMENT_EXTENSIONS:
        ext = ".pdf"
    return f"projects/plans/{uuid.uuid4().hex}{ext}"


def image_upload_to(prefix, instance, filename):
    return generate_upload_path(prefix, filename)


# Named upload_to callables (must be module-level for migration serialization).
def worker_photo_upload_to(instance, filename):
    return generate_upload_path("workers/photos", filename)


def tool_photo_upload_to(instance, filename):
    return generate_upload_path("tools/photos", filename)


def tool_media_upload_to(instance, filename):
    return generate_upload_path("tools/media", filename)


def ppe_photo_upload_to(instance, filename):
    return generate_upload_path("ppe/photos", filename)


def ppe_media_upload_to(instance, filename):
    return generate_upload_path("ppe/media", filename)


def vehicle_photo_upload_to(instance, filename):
    return generate_upload_path("vehicles/photos", filename)


def vehicle_media_upload_to(instance, filename):
    return generate_upload_path("vehicles/media", filename)
