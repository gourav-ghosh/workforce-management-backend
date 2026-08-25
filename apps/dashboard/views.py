"""Dashboard API."""

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminRole
from apps.dashboard.selectors import dashboard_summary


class DashboardAPIView(APIView):
    """GET /api/v1/dashboard/ — organisation summary for the admin home."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        return Response(dashboard_summary())
