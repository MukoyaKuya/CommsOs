from django.test import TestCase
from django.urls import reverse


class PublicTemplateTests(TestCase):
    def test_landing_page_renders_logo_for_anonymous_user(self):
        response = self.client.get(reverse("landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="CommsOS Logo"')

    def test_landing_page_exposes_three_role_dashboard_previews(self):
        response = self.client.get(reverse("landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="tablist"')
        self.assertContains(response, 'role="tab"', count=3)
        self.assertContains(response, 'role="tabpanel"', count=3)
        self.assertContains(response, "Communications Officer")
        self.assertContains(response, "Support Staff")
        self.assertContains(response, "Intern")
        self.assertContains(response, reverse("login"))
