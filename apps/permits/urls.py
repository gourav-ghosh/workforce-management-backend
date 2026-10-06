from django.urls import path

from apps.permits.views import WorkPermitDetailView, WorkPermitListCreateView

urlpatterns = [
    path("", WorkPermitListCreateView.as_view(), name="permit-list"),
    path("<int:pk>/", WorkPermitDetailView.as_view(), name="permit-detail"),
]
