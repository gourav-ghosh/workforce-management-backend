from django.urls import include, path

from apps.accounts import views

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/refresh/", views.RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path(
        "auth/password-reset/",
        views.PasswordResetRequestView.as_view(),
        name="auth-password-reset",
    ),
    path(
        "auth/password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path(
        "auth/password-reset/self/",
        views.WorkerSelfPasswordResetView.as_view(),
        name="worker-self-password-reset",
    ),
    path(
        "auth/change-password/",
        views.ChangePasswordView.as_view(),
        name="auth-change-password",
    ),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/summary/", views.MeSummaryView.as_view(), name="me-summary"),
    path("me/projects/", views.MyProjectsView.as_view(), name="me-projects"),
    path(
        "me/projects/<int:pk>/",
        views.MyProjectDetailView.as_view(),
        name="me-project-detail",
    ),
    path("me/tools/", views.MyToolsView.as_view(), name="me-tools"),
    path("me/tools/history/", views.MyToolHistoryView.as_view(), name="me-tools-history"),
    path("me/tools/<int:assignment_id>/", views.MyToolDetailView.as_view(), name="me-tool-detail"),
    path(
        "me/tools/<int:assignment_id>/damage/",
        views.MyToolDamageReportView.as_view(),
        name="me-tool-damage",
    ),
    path("me/ppe/", views.MyPPEView.as_view(), name="me-ppe"),
    path("me/vehicles/", views.MyVehiclesView.as_view(), name="me-vehicles"),
    path("me/performance/", views.MyPerformanceView.as_view(), name="me-performance"),
    path("workers/", include("apps.workers.urls")),
]
