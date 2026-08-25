"""Authentication endpoint tests."""

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from apps.accounts.models import User
from tests.utils import ADMIN_PASSWORD, WORKER_PASSWORD, BaseAPITestCase


class AuthTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.anon = APIClient()

    def login_payload(self, username="admin1", password=None):
        return {"username": username, "password": password or ADMIN_PASSWORD}

    def test_login_returns_tokens_and_user_role(self):
        response = self.anon.post("/api/v1/auth/login/", self.login_payload())
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["role"], User.Role.ADMIN)

    def test_login_worker_returns_worker_role_and_profile(self):
        response = self.anon.post(
            "/api/v1/auth/login/",
            {"username": "worker1", "password": WORKER_PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["role"], User.Role.WORKER)
        profile = response.data["user"]["worker_profile"]
        self.assertEqual(profile["employee_id"], "EMP001")

    def test_login_with_wrong_password_fails_401(self):
        response = self.anon.post("/api/v1/auth/login/", {"username": "admin1", "password": "nope"})
        self.assertEqual(response.status_code, 401)

    def test_refresh_flow(self):
        login = self.anon.post("/api/v1/auth/login/", self.login_payload())
        refresh = login.data["refresh"]
        response = self.anon.post("/api/v1/auth/refresh/", {"refresh": refresh})
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_logout_blacklists_refresh_token(self):
        login = self.anon.post("/api/v1/auth/login/", self.login_payload())
        refresh = login.data["refresh"]
        client = APIClient()
        client.force_authenticate(user=self.admin)
        logout = client.post("/api/v1/auth/logout/", {"refresh": refresh})
        self.assertEqual(logout.status_code, 204)
        reuse = self.anon.post("/api/v1/auth/refresh/", {"refresh": refresh})
        self.assertEqual(reuse.status_code, 401)

    def test_me_requires_authentication(self):
        self.assertEqual(self.anon.get("/api/v1/me/").status_code, 401)

    def test_me_returns_current_user(self):
        response = self.admin_client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "admin1")

    def test_password_reset_request_is_generic_200(self):
        response = self.anon.post(
            "/api/v1/auth/password-reset/", {"identifier": "ghost@nowhere.com"}
        )
        self.assertEqual(response.status_code, 200)

    def test_password_reset_confirm_changes_password(self):
        user = get_user_model().objects.get(username="worker1")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        response = self.anon.post(
            "/api/v1/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password": "NewStrong@99"},
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewStrong@99"))

    def test_password_reset_confirm_rejects_bad_token(self):
        user = get_user_model().objects.get(username="worker1")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        response = self.anon.post(
            "/api/v1/auth/password-reset/confirm/",
            {"uid": uid, "token": "bad-token", "new_password": "NewStrong@99"},
        )
        self.assertEqual(response.status_code, 409)

    def test_change_password_validates_current(self):
        response = self.admin_client.post(
            "/api/v1/auth/change-password/",
            {"current_password": "wrong", "new_password": "Whatever@123"},
        )
        self.assertEqual(response.status_code, 400)

        ok = self.admin_client.post(
            "/api/v1/auth/change-password/",
            {"current_password": ADMIN_PASSWORD, "new_password": "NewAdmin@123"},
        )
        self.assertEqual(ok.status_code, 200)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("NewAdmin@123"))

    def test_inactive_worker_cannot_login(self):
        inactive_profile = self.make_worker(username="worker9", employee_id="EMP009", active=False)
        response = self.anon.post(
            "/api/v1/auth/login/",
            {"username": "worker9", "password": WORKER_PASSWORD},
        )
        self.assertEqual(response.status_code, 401)
        del inactive_profile
