from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase

from accounts.selectors import active_membership_for, member_for, members_for
from core.models import Membership, Organization


class IdentitySelectorTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.org = Organization.objects.create(name="Selector Org")
        self.manager = Membership.objects.create(
            user=users.create_user("selector-manager"),
            organization=self.org,
            role=Membership.Role.COMMUNICATIONS_MANAGER,
        )
        self.member = Membership.objects.create(
            user=users.create_user("selector-member"),
            organization=self.org,
            role=Membership.Role.INTERN,
        )
        other_org = Organization.objects.create(name="Hidden Org")
        self.other_member = Membership.objects.create(
            user=users.create_user("hidden-member"),
            organization=other_org,
            role=Membership.Role.VIEWER,
        )

    def test_active_membership_returns_none_for_inactive_user(self):
        self.member.active = False
        self.member.save(update_fields=["active"])
        self.assertIsNone(active_membership_for(self.member.user))

    def test_member_selector_hides_other_organization(self):
        with self.assertRaises(Http404):
            member_for(self.manager, self.other_member.pk)

    def test_directory_contains_only_actor_organization(self):
        self.assertEqual(set(members_for(self.manager)), {self.manager, self.member})

