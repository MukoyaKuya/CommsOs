from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.policies import can_manage_members, can_view_member
from core.models import Membership, Organization


class IdentityPolicyTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.org = Organization.objects.create(name="Policy Org")
        self.manager = Membership.objects.create(
            user=users.create_user("policy-manager"),
            organization=self.org,
            role=Membership.Role.COMMUNICATIONS_MANAGER,
        )
        self.officer = Membership.objects.create(
            user=users.create_user("policy-officer"),
            organization=self.org,
            role=Membership.Role.COMMUNICATIONS_OFFICER,
        )

    def test_only_active_manager_can_manage_members(self):
        self.assertTrue(can_manage_members(self.manager))
        self.assertFalse(can_manage_members(self.officer))
        self.manager.active = False
        self.assertFalse(can_manage_members(self.manager))

    def test_member_visibility_requires_same_organization(self):
        self.assertTrue(can_view_member(self.manager, self.officer))
        other_org = Organization.objects.create(name="Other Policy Org")
        other = Membership.objects.create(
            user=get_user_model().objects.create_user("other-policy-user"),
            organization=other_org,
            role=Membership.Role.VIEWER,
        )
        self.assertFalse(can_view_member(self.manager, other))

