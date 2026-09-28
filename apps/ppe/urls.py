from django.urls import path

from apps.ppe.views import (
    PPEDetailView,
    PPEHistoryView,
    PPEIssueView,
    PPEListCreateView,
    PPEMediaView,
    PPEReturnView,
    PPESetStatusView,
    PPEStockSummaryView,
)

urlpatterns = [
    path("", PPEListCreateView.as_view(), name="ppe-list"),
    path("stock/", PPEStockSummaryView.as_view(), name="ppe-stock"),
    path("<int:pk>/", PPEDetailView.as_view(), name="ppe-detail"),
    path("<int:pk>/issue/", PPEIssueView.as_view(), name="ppe-issue"),
    path("<int:pk>/return/", PPEReturnView.as_view(), name="ppe-return"),
    path("<int:pk>/history/", PPEHistoryView.as_view(), name="ppe-history"),
    path("<int:pk>/media/", PPEMediaView.as_view(), name="ppe-media"),
    path("<int:pk>/set-status/", PPESetStatusView.as_view(), name="ppe-set-status"),
]
