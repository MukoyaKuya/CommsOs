import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q, F


class Stamp(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(Stamp):
    name = models.CharField(max_length=160)

    def __str__(self):
        return self.name


class Membership(Stamp):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Manager"
        CONTRIBUTOR = "contributor", "Contributor"
        VIEWER = "viewer", "Viewer"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=12, choices=Role.choices)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="unique_membership")
        ]


class Campaign(Stamp):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=180)
    objective = models.TextField()
    audience = models.TextField()
    geographic_focus = models.CharField(max_length=160, blank=True)
    issue = models.TextField(blank=True)
    desired_outcome = models.TextField(blank=True)
    tone = models.CharField(max_length=100, blank=True)
    channels = models.CharField(max_length=300)
    context = models.TextField(blank=True)
    starts_on = models.DateField()
    ends_on = models.DateField()
    status = models.CharField(max_length=12, default="draft")
    plan_revision = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_on__gte=F("starts_on")), name="campaign_dates_valid"
            )
        ]

    def __str__(self):
        return self.name


class Strategy(Stamp):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="strategies")
    revision = models.PositiveIntegerField()
    data = models.JSONField()
    status = models.CharField(max_length=12, default="draft")
    provenance = models.CharField(max_length=20, default="ai")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "revision"], name="unique_strategy_revision"
            )
        ]


class PlanProposal(Stamp):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    strategy = models.ForeignKey(Strategy, on_delete=models.PROTECT)
    items = models.JSONField()
    status = models.CharField(max_length=12, default="draft")


class ContentItem(Stamp):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="items")
    title = models.CharField(max_length=180)
    channel = models.CharField(max_length=40)
    format = models.CharField(max_length=60)
    pillar = models.CharField(max_length=100)
    planned_on = models.DateField()
    draft = models.TextField(blank=True)
    provenance = models.CharField(max_length=20, default="ai")

    class Meta:
        indexes = [models.Index(fields=["campaign", "planned_on"])]


class Task(Stamp):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="tasks")
    item = models.ForeignKey(ContentItem, null=True, blank=True, on_delete=models.CASCADE)
    title = models.CharField(max_length=180)
    due_on = models.DateField()
    status = models.CharField(max_length=20, default="todo")
    assignee = models.ForeignKey(Membership, null=True, blank=True, on_delete=models.SET_NULL)


class Observation(Stamp):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="observations")
    item = models.ForeignKey(ContentItem, null=True, blank=True, on_delete=models.SET_NULL)
    channel = models.CharField(max_length=40)
    format = models.CharField(max_length=60)
    observed_on = models.DateField()
    impressions = models.PositiveIntegerField(null=True, blank=True)
    engagements = models.PositiveIntegerField(null=True, blank=True)
    clicks = models.PositiveIntegerField(null=True, blank=True)
    source = models.CharField(max_length=12, default="manual")

    class Meta:
        indexes = [models.Index(fields=["campaign", "observed_on", "channel"])]


class Insight(Stamp):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    evidence = models.JSONField()
    observation_ids = models.JSONField(default=list)
    narrative = models.TextField()


class Recommendation(Stamp):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    insight = models.OneToOneField(Insight, on_delete=models.CASCADE)
    base_plan_revision = models.PositiveIntegerField()
    changes = models.JSONField()
    status = models.CharField(max_length=12, default="proposed")
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    applied_at = models.DateTimeField(null=True, blank=True)


class AuditEvent(Stamp):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=80)
    details = models.JSONField(default=dict)
