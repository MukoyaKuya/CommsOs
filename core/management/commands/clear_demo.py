from django.core.management.base import BaseCommand
from core.models import PlanProposal, Campaign, AuditEvent


class Command(BaseCommand):
    help = "Clear all campaigns, plans, content items, tasks, observations, and recommendations."

    def handle(self, *args, **options):
        PlanProposal.objects.all().delete()
        count, _ = Campaign.objects.all().delete()
        AuditEvent.objects.all().delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Cleared {count} campaign-related record(s). Workspace is now clean and empty."
            )
        )
