from django.test import TestCase
from django.urls import reverse


class PublicTemplateTests(TestCase):
    def test_landing_page_renders_logo_for_anonymous_user(self):
        response = self.client.get(reverse("landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="CommsOS Logo"')
