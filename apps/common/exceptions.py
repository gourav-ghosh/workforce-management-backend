"""Consistent API error handling."""

import logging

from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class BusinessError(APIException):
    """Raised when a workflow violates a business rule."""

    status_code = 409
    default_detail = "The request conflicts with the current state."
    default_code = "CONFLICT"


def custom_exception_handler(exc, context):
    """Wrap DRF exceptions into a consistent structure.

    Non-field errors become ``{"detail": ..., "code": ...}``; field-level
    validation errors are passed through unchanged so clients can map them
    onto form inputs.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        logger.error("Unhandled exception during request: %s", exc.__class__.__name__)
        return None

    data = getattr(response, "data", None)
    if (
        isinstance(data, dict)
        and set(data.keys()) == {"detail"}
        and isinstance(data["detail"], str)
    ):
        code = "error"
        if isinstance(exc, APIException):
            codes = exc.get_codes()
            if isinstance(codes, str):
                code = codes
        response.data["code"] = code
    return response
