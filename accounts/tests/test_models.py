from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import Invitation, StaffProfile
from core.models import Membership, Organization


class IdentityModelTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user("identity-user", password="test-password")
        self.manager_user = user_model.objects.create_user("identity-manager", password="test-password")
        self.org = Organization.objects.create(name="Identity Org")
        self.other_org = Organization.objects.create(name="Other Org")
        self.manager = Membership.objects.create(
            user=self.manager_user,
            organization=self.org,
            role=Membership.Role.COMMUNICATIONS_MANAGER,
        )

    def test_user_can_have_only_one_membership(self):
        Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=Membership.Role.COMMUNICATIONS_OFFICER,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(
                    user=self.user,
                    organization=self.other_org,
                    role=Membership.Role.VIEWER,
                )

    def test_profile_rejects_self_supervisor(self):
        membership = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=Membership.Role.INTERN,
        )
        profile = StaffProfile(membership=membership, supervisor=membership)

        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_profile_rejects_supervisor_from_another_organization(self):
        membership = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=Membership.Role.INTERN,
        )
        other_user = get_user_model().objects.create_user("other-manager")
        other_manager = Membership.objects.create(
            user=other_user,
            organization=self.other_org,
            role=Membership.Role.COMMUNICATIONS_MANAGER,
        )
        profile = StaffProfile(membership=membership, supervisor=other_manager)

        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_invitation_hashes_raw_token_and_normalizes_email(self):
        invitation, raw_token = Invitation.issue(
            organization=self.org,
            email="  Officer@Example.COM ",
            role=Membership.Role.COMMUNICATIONS_OFFICER,
            invited_by=self.manager,
        )

        self.assertEqual(invitation.email, "Officer@example.com")
        self.assertNotEqual(invitation.token_hash, raw_token)
        self.assertTrue(invitation.matches(raw_token))
        self.assertFalse(invitation.matches("wrong-token"))

