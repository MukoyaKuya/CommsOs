from django.core.management import call_command
from django.test import TestCase

from accounts.models import StaffProfile
from core.models import Membership


class SeedDemoTests(TestCase):
    def test_seed_demo_creates_all_roles_without_duplicates(self):
        call_command("seed_demo", password="A-strong-test-password-2026")
        call_command("seed_demo", password="A-strong-test-password-2026")

        self.assertEqual(Membership.objects.count(), 5)
        self.assertEqual(set(Membership.objects.values_list("role", flat=True)), set(Membership.Role.values))
        self.assertEqual(StaffProfile.objects.count(), 5)

