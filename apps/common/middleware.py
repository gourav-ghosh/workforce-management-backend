"""Custom middleware that rewrites the request host for URL building.

When ``PUBLIC_BASE_URL`` is configured, mobile clients (Android emulator,
phones on the same LAN, the Flutter web build, etc.) all see absolute media
URLs that match the host they're connecting through. Without this, the
default behaviour uses the request's ``Host`` header, which is fine for
browser-based DRF Browsable API calls on the host but produces a URL the
mobile app can't fetch (e.g. ``localhost`` from a phone, ``127.0.0.1`` from
the Android emulator).

The middleware mutates ``request.META['HTTP_HOST']`` (and the scheme) only
when ``PUBLIC_BASE_URL`` is non-empty, so the rest of Django is unaware
that anything happened.
"""

from urllib.parse import urlparse

from django.conf import settings


class PublicHostMiddleware:
    """Rewrite the request host so ``request.build_absolute_uri(...)``
    returns a URL the caller can actually fetch.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._parsed = urlparse(settings.PUBLIC_BASE_URL) if settings.PUBLIC_BASE_URL else None

    def __call__(self, request):
        if self._parsed is not None and self._parsed.netloc:
            request.META["HTTP_HOST"] = self._parsed.netloc
            if self._parsed.scheme:
                # ``WSGIRequest._get_scheme`` reads ``wsgi.url_scheme`` from
                # the WSGI environ, which ``request.META`` aliases. We also
                # set ``HTTPS=on`` so ``request.is_secure()`` returns True on
                # plain ``HttpRequest`` instances (e.g. ``RequestFactory``).
                request.META["wsgi.url_scheme"] = self._parsed.scheme
                if self._parsed.scheme == "https":
                    request.META["HTTPS"] = "on"
        return self.get_response(request)
