from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from platform_api.auth_utils import ensure_admin_user


@override_settings(
    DJANGO_ADMIN_EMAIL="operator@example.com",
    DJANGO_ADMIN_PASSWORD="super-secret-password",
)
class AuthApiTests(APITestCase):
    def setUp(self):
        ensure_admin_user()
        self.client = APIClient()

    def test_can_login_and_read_session(self):
        response = self.client.post(
            "/api/v1/admin/session",
            {"email": settings.DJANGO_ADMIN_EMAIL, "password": settings.DJANGO_ADMIN_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["isAuthenticated"])

        session_response = self.client.get("/api/v1/admin/session")
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.data["email"], settings.DJANGO_ADMIN_EMAIL)
