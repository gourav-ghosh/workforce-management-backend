from django.urls import path

from apps.attendance.views import AttendanceDetailView, AttendanceListCreateView

urlpatterns = [
    path("", AttendanceListCreateView.as_view(), name="attendance-list"),
    path("<int:pk>/", AttendanceDetailView.as_view(), name="attendance-detail"),
]
