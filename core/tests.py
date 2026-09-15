from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch
from .analytics import evidence_for
from .ai import AIError, explain
from .models import (
    Organization,
    Membership,
    Campaign,
    Observation,
    ContentItem,
    Task,
    AuditEvent,
)
from . import services


class CampaignFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("manager", password="safe-test-password")
        self.other = get_user_model().objects.create_user("other", password="safe-test-password")
        self.org = Organization.objects.create(name="One")
        self.other_org = Organization.objects.create(name="Two")
        Membership.objects.create(user=self.user, organization=self.org, role="manager")
        Membership.objects.create(user=self.other, organization=self.other_org, role="manager")
        self.campaign = Campaign.objects.create(
            organization=self.org,
            name="Safety",
            objective="Improve scam awareness",
            audience="Students",
            channels="TikTok, Instagram",
            starts_on=date.today(),
            ends_on=date.today() + timedelta(days=29),
        )

    def test_cross_organization_is_not_visible(self):
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(reverse("campaign_detail", args=[self.campaign.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("strategy_generate", args=[self.campaign.pk])).status_code,
            404,
        )

    def test_dashboard_summarizes_workspace_records(self):
        self.campaign.status = "active"
        self.campaign.save(update_fields=["status"])
        item = ContentItem.objects.create(
            campaign=self.campaign,
            title="Launch video",
            channel="TikTok",
            format="short video",
            pillar="Protect",
            planned_on=date.today() + timedelta(days=1),
            draft="Ready for review",
        )
        Task.objects.create(
            campaign=self.campaign,
            item=item,
            title="Approve launch video",
            due_on=date.today(),
            status="done",
        )
        Task.objects.create(
            campaign=self.campaign,
            title="Review results",
            due_on=date.today() + timedelta(days=2),
            status="todo",
        )
        Observation.objects.create(
            campaign=self.campaign,
            channel="TikTok",
            format="short video",
            observed_on=date.today(),
            impressions=100,
            engagements=20,
        )
        AuditEvent.objects.create(
            organization=self.org,
            campaign=self.campaign,
            actor=self.user,
            action="campaign_created",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["dashboard_metrics"]["active_campaigns"], 1)
        self.assertEqual(response.context["dashboard_metrics"]["task_completion"], 50)
        self.assertEqual(response.context["dashboard_metrics"]["content_count"], 1)
        self.assertEqual(response.context["dashboard_metrics"]["engagement_rate"], 20.0)
        self.assertEqual(list(response.context["upcoming_items"]), [item])
        self.assertEqual(len(response.context["recent_activity"]), 1)

    def test_dashboard_exposes_named_overview(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, 'aria-label="Dashboard overview"')

    def test_dashboard_renders_vector_icons_for_navigation(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, 'class="lucide lucide-house"')
        self.assertNotContains(response, "⌂ Overview")

    def test_strategy_plan_and_recommendation_are_persisted_once(self):
        strategy = services.generate_strategy(self.user, self.campaign)
        self.assertEqual(strategy.status, "draft")
        services.approve_strategy(self.user, self.campaign)
        proposal = services.generate_plan(self.user, self.campaign)
        self.assertEqual(len(proposal.items), 4)
        services.apply_plan(self.user, self.campaign)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.plan_revision, 1)
        self.assertEqual(ContentItem.objects.filter(campaign=self.campaign).count(), 4)
        Observation.objects.create(
            campaign=self.campaign,
            channel="TikTok",
            format="short video",
            observed_on=date.today(),
            impressions=100,
            engagements=12,
        )
        Observation.objects.create(
            campaign=self.campaign,
            channel="Instagram",
            format="carousel",
            observed_on=date.today(),
            impressions=100,
            engagements=4,
        )
        rec = services.generate_insight(self.user, self.campaign)
        self.assertEqual(rec.base_plan_revision, 1)
        services.apply_recommendation(self.user, self.campaign)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.plan_revision, 2)
        self.assertEqual(ContentItem.objects.filter(campaign=self.campaign).count(), 5)
        with self.assertRaises(ValidationError):
            services.apply_recommendation(self.user, self.campaign)
        self.assertEqual(ContentItem.objects.filter(campaign=self.campaign).count(), 5)

    def test_sparse_data_does_not_claim_comparison(self):
        Observation.objects.create(
            campaign=self.campaign,
            channel="TikTok",
            format="video",
            observed_on=date.today(),
            impressions=100,
            engagements=12,
        )
        self.assertIsNone(evidence_for(self.campaign)[0])

    def test_ai_insight_rejects_unverified_numbers(self):
        with patch(
            "core.ai._request",
            return_value={"narrative": "Engagement rose 90%.", "recommendation": "Add a video."},
        ):
            with self.assertRaises(AIError):
                explain({"winner": "TikTok / video", "groups": []})

    def test_contributor_cannot_approve(self):
        contributor = get_user_model().objects.create_user(
            "contributor", password="safe-test-password"
        )
        Membership.objects.create(user=contributor, organization=self.org, role="contributor")
        with self.assertRaises(PermissionDenied):
            services.generate_strategy(contributor, self.campaign)

    def test_brief_change_requires_new_strategy(self):
        services.generate_strategy(self.user, self.campaign)
        services.approve_strategy(self.user, self.campaign)
        values = {
            field: getattr(self.campaign, field)
            for field in (
                "name",
                "objective",
                "audience",
                "geographic_focus",
                "issue",
                "desired_outcome",
                "tone",
                "channels",
                "context",
                "starts_on",
                "ends_on",
            )
        }
        values["objective"] = "A revised objective"
        services.update_campaign(self.user, self.campaign, values)
        self.assertFalse(self.campaign.strategies.filter(status="approved").exists())
        with self.assertRaises(ValidationError):
            services.generate_plan(self.user, self.campaign)

    def test_stale_recommendation_cannot_change_plan(self):
        services.generate_strategy(self.user, self.campaign)
        services.approve_strategy(self.user, self.campaign)
        Observation.objects.create(
            campaign=self.campaign,
            channel="TikTok",
            format="video",
            observed_on=date.today(),
            impressions=100,
            engagements=12,
        )
        Observation.objects.create(
            campaign=self.campaign,
            channel="Instagram",
            format="carousel",
            observed_on=date.today(),
            impressions=100,
            engagements=4,
        )
        services.generate_insight(self.user, self.campaign)
        self.campaign.plan_revision = 1
        self.campaign.save(update_fields=["plan_revision"])
        with self.assertRaises(ValidationError):
            services.apply_recommendation(self.user, self.campaign)
        self.assertEqual(ContentItem.objects.filter(campaign=self.campaign).count(), 0)

    def test_editing_plan_item_invalidates_old_recommendation(self):
        services.generate_strategy(self.user, self.campaign)
        services.approve_strategy(self.user, self.campaign)
        services.generate_plan(self.user, self.campaign)
        services.apply_plan(self.user, self.campaign)
        self.campaign.refresh_from_db()
        item = ContentItem.objects.filter(campaign=self.campaign).first()
        Observation.objects.create(
            campaign=self.campaign,
            channel="TikTok",
            format="video",
            observed_on=date.today(),
            impressions=100,
            engagements=12,
        )
        Observation.objects.create(
            campaign=self.campaign,
            channel="Instagram",
            format="carousel",
            observed_on=date.today(),
            impressions=100,
            engagements=4,
        )
        services.generate_insight(self.user, self.campaign)
        services.update_content(
            self.user,
            self.campaign,
            item,
            {
                "title": "Edited title",
                "channel": item.channel,
                "format": item.format,
                "pillar": item.pillar,
                "planned_on": item.planned_on,
                "draft": item.draft,
            },
        )
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.plan_revision, 2)
        with self.assertRaises(ValidationError):
            services.apply_recommendation(self.user, self.campaign)

    def test_campaigns_list_renders_for_authorized_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("campaigns_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Campaigns")
        self.assertContains(response, self.campaign.name)
        self.assertEqual(response.context["metrics"]["total"], 1)

    def test_campaigns_list_cross_org_isolation(self):
        other_campaign = Campaign.objects.create(
            organization=self.other_org,
            name="Secret Two",
            objective="Other objective",
            audience="Other audience",
            channels="Email",
            starts_on=date.today(),
            ends_on=date.today() + timedelta(days=10),
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("campaigns_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.campaign.name)
        self.assertNotContains(response, "Secret Two")

    def test_calendar_view_renders_for_authorized_user(self):
        from core.models import CalendarEvent
        CalendarEvent.objects.create(
            organization=self.org,
            title="Team stand-up",
            event_type="team",
            date=date.today(),
            created_by=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("calendar_view"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Calendar")
        self.assertContains(response, "Team stand-up")

    def test_calendar_event_create_and_isolation(self):
        from core.models import CalendarEvent
        self.client.force_login(self.user)
        post_data = {
            "title": "Strategy Sync",
            "event_type": "campaigns",
            "date": date.today().strftime("%Y-%m-%d"),
            "start_time": "10:00",
            "end_time": "11:00",
        }
        res = self.client.post(reverse("calendar_event_create"), post_data, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(CalendarEvent.objects.filter(title="Strategy Sync", organization=self.org).exists())

        # Verify other organization cannot see this event
        self.client.force_login(self.other)
        other_res = self.client.get(reverse("calendar_view"))
        self.assertEqual(other_res.status_code, 200)
        self.assertNotContains(other_res, "Strategy Sync")


