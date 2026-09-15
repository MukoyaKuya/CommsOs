from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from core.models import Organization, Membership, Campaign, Observation


class Command(BaseCommand):
    help = "Create a clearly labeled demonstration organization and campaign."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            required=True,
            help="Password for demo accounts; use a throwaway value only.",
        )

    def handle(self, *args, **options):
        org, _ = Organization.objects.get_or_create(name="CommsOS Demo")
        for username, role in [
            ("demo_owner", "owner"),
            ("demo_manager", "manager"),
            ("demo_contributor", "contributor"),
        ]:
            user, _ = get_user_model().objects.get_or_create(username=username)
            user.set_password(options["password"])
            user.save()
            Membership.objects.update_or_create(
                organization=org, user=user, defaults={"role": role, "active": True}
            )
        start = date.today()
        campaign, _ = Campaign.objects.get_or_create(
            organization=org,
            name="Think Before You Click",
            defaults={
                "objective": "Increase awareness of common online scams among Kenyan university students.",
                "audience": "Kenyan university students aged 18–25",
                "geographic_focus": "Kenya",
                "issue": "Online scams",
                "desired_outcome": "Recognize and avoid common scam attempts",
                "tone": "Clear and practical",
                "channels": "TikTok, Instagram, WhatsApp, Website",
                "starts_on": start,
                "ends_on": start + timedelta(days=29),
            },
        )
        if not campaign.observations.exists():
            for days_ago, channel, fmt, impressions, engagements in [
                (6, "Instagram", "carousel", 1500, 75),
                (4, "Instagram", "carousel", 2000, 90),
                (2, "TikTok", "short video", 1800, 216),
                (0, "TikTok", "short video", 2200, 242),
            ]:
                Observation.objects.create(
                    campaign=campaign,
                    channel=channel,
                    format=fmt,
                    observed_on=start - timedelta(days=days_ago),
                    impressions=impressions,
                    engagements=engagements,
                    source="demo",
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo ready: {campaign.id}. Accounts: demo_owner, demo_manager, demo_contributor."
            )
        )
