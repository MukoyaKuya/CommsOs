from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.exceptions import (
    CrossOrganizationAccess,
    InvitationAlreadyUsed,
    InvitationExpired,
    LastManagerRequired,
    PermissionDenied,
)
from accounts.models import StaffProfile
from accounts.services import (
    accept_invitation,
    create_invitation,
    deactivate_member,
    update_staff_profile,
)
from core.models import Membership, Organization


class IdentityServiceTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.org = Organization.objects.create(name="Service Org")
        self.manager = Membership.objects.create(
            user=users.create_user("service-manager", email="manager@example.com"),
            organization=self.org,
            role=Membership.Role.COMMUNICATIONS_MANAGER,
        )
        StaffProfile.objects.create(membership=self.manager)
        self.officer = Membership.objects.create(
            user=users.create_user("service-officer", email="officer@example.com"),
            organization=self.org,
            role=Membership.Role.COMMUNICATIONS_OFFICER,
        )
        StaffProfile.objects.create(membership=self.officer)

    def test_manager_invitation_is_single_use_and_creates_profile(self):
        invitation, token = create_invitation(
            self.manager,
            "new@example.com",
            Membership.Role.COMMUNICATIONS_OFFICER,
            {"job_title": "Officer", "skills": ["writing"]},
        )

        membership = accept_invitation(
            token,
            username="new-officer",
            password="A-strong-test-password-2026",
        )

        self.assertEqual(membership.organization, self.org)
        self.assertEqual(membership.staff_profile.job_title, "Officer")
        self.assertEqual(membership.staff_profile.skills, ["writing"])
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.accepted_at)
        with self.assertRaises(InvitationAlreadyUsed):
            accept_invitation(token, "duplicate", "A-strong-test-password-2026")

    def test_non_manager_cannot_invite(self):
        with self.assertRaises(PermissionDenied):
            create_invitation(
                self.officer,
                "blocked@example.com",
                Membership.Role.INTERN,
                {},
            )

    def test_expired_invitation_cannot_be_accepted(self):
        invitation, token = create_invitation(
            self.manager, "expired@example.com", Membership.Role.INTERN, {}
        )
        invitation.expires_at = timezone.now() - timedelta(seconds=1)
        invitation.save(update_fields=["expires_at"])
        with self.assertRaises(InvitationExpired):
            accept_invitation(token, "expired", "A-strong-test-password-2026")

    def test_last_manager_cannot_be_deactivated(self):
        with self.assertRaises(LastManagerRequired):
            deactivate_member(self.manager, self.manager.pk)

    def test_manager_cannot_modify_other_organization_profile(self):
        other_org = Organization.objects.create(name="Other Service Org")
        other_member = Membership.objects.create(
            user=get_user_model().objects.create_user("other-service-user"),
            organization=other_org,
            role=Membership.Role.INTERN,
        )
        StaffProfile.objects.create(membership=other_member)
        with self.assertRaises(CrossOrganizationAccess):
            update_staff_profile(self.manager, other_member.pk, {"rank": "Senior"})

