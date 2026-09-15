from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Invitation, StaffProfile
from core.models import Membership, Organization


class TeamManagementViewTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.org = Organization.objects.create(name="Views Org")
        self.manager = Membership.objects.create(
            user=users.create_user("views-manager", email="manager@views.test"),
            organization=self.org,
            role=Membership.Role.COMMUNICATIONS_MANAGER,
        )
        StaffProfile.objects.create(membership=self.manager)
        self.officer = Membership.objects.create(
            user=users.create_user("views-officer", email="officer@views.test"),
            organization=self.org,
            role=Membership.Role.COMMUNICATIONS_OFFICER,
        )
        StaffProfile.objects.create(membership=self.officer)

    def test_manager_can_create_invitation_from_team_page(self):
        self.client.force_login(self.manager.user)
        response = self.client.post(
            reverse("invitation_create"),
            {
                "email": "staff@example.com",
                "role": Membership.Role.SUPPORT_STAFF,
                "job_title": "Driver",
                "department": "Transport",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Copy this invitation link")
        self.assertTrue(Invitation.objects.filter(email="staff@example.com").exists())

    def test_officer_cannot_open_team_directory(self):
        self.client.force_login(self.officer.user)
        self.assertEqual(self.client.get(reverse("team_directory")).status_code, 403)

    def test_public_invitation_acceptance_creates_account(self):
        invitation, token = Invitation.issue(
            self.org,
            "intern@example.com",
            Membership.Role.INTERN,
            self.manager,
        )
        response = self.client.post(
            reverse("invitation_accept", args=[token]),
            {
                "username": "accepted-intern",
                "first_name": "Accepted",
                "last_name": "Intern",
                "password1": "A-strong-test-password-2026",
                "password2": "A-strong-test-password-2026",
            },
        )
        self.assertRedirects(response, reverse("login"))
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.accepted_at)

    def test_manager_can_deactivate_and_reactivate_member(self):
        self.client.force_login(self.manager.user)
        response = self.client.post(reverse("member_deactivate", args=[self.officer.pk]))
        self.assertRedirects(response, reverse("team_directory"))
        self.officer.refresh_from_db()
        self.assertFalse(self.officer.active)
        response = self.client.post(reverse("member_reactivate", args=[self.officer.pk]))
        self.assertRedirects(response, reverse("team_directory"))
        self.officer.refresh_from_db()
        self.assertTrue(self.officer.active)
