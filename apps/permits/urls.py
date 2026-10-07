from django.urls import path

from apps.permits.views import (
    WorkPermitDetailView,
    WorkPermitListCreateView,
    WorkPermitMonthlySummaryView,
)

urlpatterns = [
    path("", WorkPermitListCreateView.as_view(), name="permit-list"),
    # Declared before the <int:pk> route so "summary" is not read as a pk.
    path("summary/", WorkPermitMonthlySummaryView.as_view(), name="permit-summary"),
    path("<int:pk>/", WorkPermitDetailView.as_view(), name="permit-detail"),
]
