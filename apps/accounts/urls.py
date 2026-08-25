from django.urls import path

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
        "auth/change-password/",
        views.ChangePasswordView.as_view(),
        name="auth-change-password",
    ),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/summary/", views.MeSummaryView.as_view(), name="me-summary"),
    path("me/projects/", views.MyProjectsView.as_view(), name="me-projects"),
    path("me/tools/", views.MyToolsView.as_view(), name="me-tools"),
    path("me/ppe/", views.MyPPEView.as_view(), name="me-ppe"),
    path("me/vehicles/", views.MyVehiclesView.as_view(), name="me-vehicles"),
]
