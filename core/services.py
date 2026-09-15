from datetime import date, timedelta
import os
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from . import ai
from .analytics import evidence_for
from .models import (
    Strategy,
    PlanProposal,
    ContentItem,
    Task,
    Insight,
    Recommendation,
    AuditEvent,
    Campaign,
    Membership,
    Observation,
)
from .selectors import can_manage


def require_manager(user, campaign):
    if not can_manage(user, campaign):
        raise PermissionDenied


def audit(user, campaign, action, details=None):
    AuditEvent.objects.create(
        actor=user,
        organization=campaign.organization,
        campaign=campaign,
        action=action,
        details=details or {},
    )


@transaction.atomic
def create_campaign(user, values):
    membership = (
        Membership.objects.select_related("organization")
        .filter(user=user, active=True, role__in=["owner", "manager"])
        .first()
    )
    if not membership:
        raise PermissionDenied
    campaign = Campaign.objects.create(organization=membership.organization, **values)
    audit(user, campaign, "campaign_created")
    return campaign


@transaction.atomic
def update_campaign(user, campaign, values):
    require_manager(user, campaign)
    locked = Campaign.objects.select_for_update().get(pk=campaign.pk)
    if locked.plan_revision:
        raise ValidationError(
            "Brief editing is locked after a plan is applied. Create a new campaign to change the brief."
        )
    changed = any(getattr(locked, key) != value for key, value in values.items())
    for key, value in values.items():
        setattr(locked, key, value)
    locked.save()
    if changed:
        Strategy.objects.filter(campaign=locked, status="approved").update(status="superseded")
        PlanProposal.objects.filter(campaign=locked, status="draft").update(status="stale")
        audit(user, locked, "brief_updated")
    return locked


@transaction.atomic
def add_observation(user, campaign, values):
    require_manager(user, campaign)
    channels = {x.strip().lower() for x in campaign.channels.split(",")}
    if values["channel"].strip().lower() not in channels:
        raise ValidationError("Choose a campaign channel.")
    observation = Observation.objects.create(campaign=campaign, source="manual", **values)
    audit(user, campaign, "observation_added", {"observation": str(observation.pk)})
    return observation


def generate_strategy(user, campaign):
    require_manager(user, campaign)
    data = ai.strategy(campaign)
    with transaction.atomic():
        last = Strategy.objects.filter(campaign=campaign).order_by("-revision").first()
        result = Strategy.objects.create(
            campaign=campaign,
            revision=last.revision + 1 if last else 1,
            data=data,
            provenance="demo" if os.getenv("AI_MODE", "demo") == "demo" else "ai",
        )
        audit(user, campaign, "strategy_generated", {"revision": result.revision})
    return result


@transaction.atomic
def update_strategy(user, campaign, strategy, values):
    require_manager(user, campaign)
    locked = Strategy.objects.select_for_update().get(pk=strategy.pk, campaign=campaign)
    if locked.status != "draft":
        raise ValidationError("Only a draft strategy can be edited.")
    data = dict(locked.data)
    data.update(values)
    locked.data = data
    locked.save(update_fields=["data", "updated_at"])
    audit(user, campaign, "strategy_edited", {"revision": locked.revision})
    return locked


@transaction.atomic
def approve_strategy(user, campaign):
    require_manager(user, campaign)
    draft = (
        Strategy.objects.select_for_update()
        .filter(campaign=campaign, status="draft")
        .order_by("-revision")
        .first()
    )
    if not draft:
        raise ValidationError("No draft strategy is available.")
    Strategy.objects.filter(campaign=campaign, status="approved").update(status="superseded")
    draft.status = "approved"
    draft.approved_by = user
    draft.approved_at = timezone.now()
    draft.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    audit(user, campaign, "strategy_approved", {"revision": draft.revision})
    return draft


def validate_items(campaign, items, strategy):
    allowed = {x.strip().lower() for x in campaign.channels.split(",")}
    pillars = {x.lower() for x in strategy.data["pillars"]}
    clean = []
    for item in items:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(k), str) or not item[k].strip()
            for k in ("title", "channel", "format", "pillar", "planned_on")
        ):
            raise ValidationError("Plan has an incomplete item.")
        try:
            day = date.fromisoformat(item["planned_on"])
        except ValueError:
            raise ValidationError("Plan has an invalid date.")
        if (
            not campaign.starts_on <= day <= campaign.ends_on
            or item["channel"].lower() not in allowed
            or item["pillar"].lower() not in pillars
        ):
            raise ValidationError("Plan item is outside the approved campaign context.")
        clean.append(
            {
                k: item[k].strip()[:180]
                for k in ("title", "channel", "format", "pillar", "planned_on")
            }
        )
    return clean


def generate_plan(user, campaign):
    require_manager(user, campaign)
    strategy = (
        Strategy.objects.filter(campaign=campaign, status="approved").order_by("-revision").first()
    )
    if not strategy:
        raise ValidationError("Approve a strategy first.")
    items = validate_items(campaign, ai.plan(campaign, strategy.data), strategy)
    proposal = PlanProposal.objects.create(campaign=campaign, strategy=strategy, items=items)
    audit(user, campaign, "plan_generated", {"proposal": str(proposal.id)})
    return proposal


@transaction.atomic
def apply_plan(user, campaign):
    require_manager(user, campaign)
    locked = Campaign.objects.select_for_update().get(pk=campaign.pk)
    proposal = (
        PlanProposal.objects.select_for_update()
        .filter(campaign=locked, status="draft")
        .order_by("-created_at")
        .first()
    )
    if not proposal:
        raise ValidationError("No draft plan is available.")
    for data in validate_items(locked, proposal.items, proposal.strategy):
        item = ContentItem.objects.create(
            campaign=locked, **data, provenance=proposal.strategy.provenance
        )
        Task.objects.create(
            campaign=locked,
            item=item,
            title=f"Produce {item.title}",
            due_on=item.planned_on,
        )
    proposal.status = "applied"
    proposal.save(update_fields=["status", "updated_at"])
    locked.plan_revision += 1
    locked.save(update_fields=["plan_revision", "updated_at"])
    audit(user, locked, "plan_applied", {"revision": locked.plan_revision})
    return locked


def generate_content(user, campaign, item):
    require_manager(user, campaign)
    strategy = (
        Strategy.objects.filter(campaign=campaign, status="approved").order_by("-revision").first()
    )
    if not strategy:
        raise ValidationError("Approve a strategy first.")
    draft = ai.content(campaign, item, strategy.data)
    item.draft = draft
    item.save(update_fields=["draft", "updated_at"])
    audit(user, campaign, "content_generated", {"item": str(item.id)})
    return item


@transaction.atomic
def update_content(user, campaign, item, values):
    require_manager(user, campaign)
    locked_campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    locked_item = ContentItem.objects.select_for_update().get(pk=item.pk, campaign=locked_campaign)
    strategy = (
        Strategy.objects.filter(campaign=locked_campaign, status="approved")
        .order_by("-revision")
        .first()
    )
    allowed_channels = {x.strip().lower() for x in locked_campaign.channels.split(",")}
    pillars = {x.lower() for x in strategy.data["pillars"]} if strategy else set()
    if not locked_campaign.starts_on <= values["planned_on"] <= locked_campaign.ends_on:
        raise ValidationError("Date must be within the campaign period.")
    if values["channel"].strip().lower() not in allowed_channels:
        raise ValidationError("Choose a campaign channel.")
    if values["pillar"].strip().lower() not in pillars:
        raise ValidationError("Choose an approved strategy pillar.")
    plan_fields = ("title", "channel", "format", "pillar", "planned_on")
    changed_plan = any(getattr(locked_item, key) != values[key] for key in plan_fields)
    for key in (*plan_fields, "draft"):
        setattr(locked_item, key, values[key])
    locked_item.save()
    if changed_plan:
        locked_campaign.plan_revision += 1
        locked_campaign.save(update_fields=["plan_revision", "updated_at"])
    audit(
        user,
        locked_campaign,
        "content_edited",
        {"item": str(item.id), "plan_revision": locked_campaign.plan_revision},
    )
    return locked_item


def generate_insight(user, campaign):
    require_manager(user, campaign)
    evidence, ids = evidence_for(campaign)
    if not evidence:
        raise ValidationError(
            "Add performance data with positive impressions and engagements first."
        )
    narrative, suggestion = ai.explain(evidence)
    winner = evidence["groups"][0]
    channel, format_name = winner["name"].split(" / ", 1)
    strategy = (
        Strategy.objects.filter(campaign=campaign, status="approved").order_by("-revision").first()
    )
    if not strategy:
        raise ValidationError("Approve a strategy first.")
    proposed_date = max(
        campaign.starts_on,
        min(campaign.ends_on, timezone.localdate() + timedelta(days=1)),
    )
    change = {
        "title": f"Test: {format_name} follow-up",
        "channel": channel,
        "format": format_name,
        "pillar": strategy.data["pillars"][0],
        "planned_on": proposed_date.isoformat(),
    }
    with transaction.atomic():
        insight = Insight.objects.create(
            campaign=campaign,
            evidence=evidence,
            observation_ids=ids,
            narrative=narrative,
        )
        rec = Recommendation.objects.create(
            campaign=campaign,
            insight=insight,
            base_plan_revision=campaign.plan_revision,
            changes=[change],
        )
        audit(
            user,
            campaign,
            "recommendation_proposed",
            {"recommendation": str(rec.id), "suggestion": suggestion},
        )
    return rec


@transaction.atomic
def apply_recommendation(user, campaign):
    require_manager(user, campaign)
    locked = Campaign.objects.select_for_update().get(pk=campaign.pk)
    rec = (
        Recommendation.objects.select_for_update()
        .filter(campaign=locked, status="proposed")
        .order_by("-created_at")
        .first()
    )
    if not rec:
        raise ValidationError("No unapplied recommendation is available.")
    if rec.base_plan_revision != locked.plan_revision:
        raise ValidationError("The plan changed. Generate a fresh recommendation.")
    strategy = (
        Strategy.objects.filter(campaign=locked, status="approved").order_by("-revision").first()
    )
    for data in validate_items(locked, rec.changes, strategy):
        item = ContentItem.objects.create(campaign=locked, provenance="recommendation", **data)
        Task.objects.create(
            campaign=locked,
            item=item,
            title=f"Produce {item.title}",
            due_on=item.planned_on,
        )
    locked.plan_revision += 1
    locked.save(update_fields=["plan_revision", "updated_at"])
    rec.status = "applied"
    rec.applied_by = user
    rec.applied_at = timezone.now()
    rec.save(update_fields=["status", "applied_by", "applied_at", "updated_at"])
    audit(
        user,
        locked,
        "recommendation_applied",
        {"recommendation": str(rec.id), "revision": locked.plan_revision},
    )
    return rec
