from django.urls import path

from apps.tools.views import (
    ToolDamageView,
    ToolDetailView,
    ToolHistoryView,
    ToolIssueView,
    ToolListCreateView,
    ToolMediaView,
    ToolRepairView,
    ToolReturnView,
    ToolSetStatusView,
    ToolStockSummaryView,
)

urlpatterns = [
    path("", ToolListCreateView.as_view(), name="tool-list"),
    path("stock/", ToolStockSummaryView.as_view(), name="tool-stock"),
    path("<int:pk>/", ToolDetailView.as_view(), name="tool-detail"),
    path("<int:pk>/issue/", ToolIssueView.as_view(), name="tool-issue"),
    path("<int:pk>/return/", ToolReturnView.as_view(), name="tool-return"),
    path("<int:pk>/damage/", ToolDamageView.as_view(), name="tool-damage"),
    path("<int:pk>/history/", ToolHistoryView.as_view(), name="tool-history"),
    path("<int:pk>/media/", ToolMediaView.as_view(), name="tool-media"),
    path("<int:pk>/set-status/", ToolSetStatusView.as_view(), name="tool-set-status"),
    path("<int:pk>/repair/", ToolRepairView.as_view(), name="tool-repair"),
]
