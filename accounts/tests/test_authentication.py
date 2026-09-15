from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Membership, Organization


class RoleAuthenticationTests(TestCase):
    password = "A-strong-test-password-2026"

    def setUp(self):
        self.org = Organization.objects.create(name="Auth Org")

    def create_member(self, username, role, active=True):
        user = get_user_model().objects.create_user(username, password=self.password)
        Membership.objects.create(user=user, organization=self.org, role=role, active=active)
        return user

    def test_login_rejects_role_mismatch_without_revealing_actual_role(self):
        user = self.create_member("role-user", Membership.Role.COMMUNICATIONS_OFFICER)
        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": self.password, "role": Membership.Role.INTERN},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unable to sign in with those details")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_each_role_routes_to_its_dashboard(self):
        cases = [
            (Membership.Role.COMMUNICATIONS_MANAGER, "dashboard.html"),
            (Membership.Role.COMMUNICATIONS_OFFICER, "accounts/dashboard_officer.html"),
            (Membership.Role.SUPPORT_STAFF, "accounts/dashboard_support.html"),
            (Membership.Role.INTERN, "accounts/dashboard_intern.html"),
            (Membership.Role.VIEWER, "accounts/dashboard_viewer.html"),
        ]
        for index, (role, template) in enumerate(cases):
            with self.subTest(role=role):
                user = self.create_member(f"dashboard-{index}", role)
                self.client.force_login(user)
                response = self.client.get(reverse("dashboard"))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)
                self.client.logout()

    def test_deactivated_member_cannot_enter_dashboard(self):
        user = self.create_member("inactive-user", Membership.Role.INTERN, active=False)
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 403)
