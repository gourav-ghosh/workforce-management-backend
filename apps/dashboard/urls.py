from django.urls import path

from apps.dashboard.views import DashboardAPIView

urlpatterns = [
    path("", DashboardAPIView.as_view(), name="dashboard"),
]
