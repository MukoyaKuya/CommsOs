from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseNotAllowed
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from django.utils import timezone
from .forms import CampaignForm, ObservationForm, StrategyEditForm, ContentItemForm
from .models import (
    Campaign,
    ContentItem,
    Strategy,
    PlanProposal,
    Insight,
    Recommendation,
    Task,
    ContentItem,
    Observation,
    AuditEvent,
)
from .selectors import membership_for, campaign_for, can_manage
from . import services
from .analytics import evidence_for
from .ai import AIError


def post_only(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    return None


def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "landing.html")


@login_required
def dashboard(request):
    membership = membership_for(request.user)
    if not membership:
        return render(
            request,
            "dashboard.html",
            {
                "membership": None,
                "campaigns": [],
                "dashboard_metrics": {},
                "my_tasks": [],
                "upcoming_items": [],
                "recent_activity": [],
                "channel_performance": [],
            },
        )

    organization = membership.organization
    campaigns = list(Campaign.objects.filter(organization=organization).order_by("-created_at"))
    campaign_ids = [campaign.pk for campaign in campaigns]
    tasks = Task.objects.filter(campaign_id__in=campaign_ids)
    task_total = tasks.count()
    task_done = tasks.filter(status="done").count()
    observations = Observation.objects.filter(campaign_id__in=campaign_ids)
    totals = observations.aggregate(impressions=Sum("impressions"), engagements=Sum("engagements"))
    impressions = totals["impressions"] or 0
    engagements = totals["engagements"] or 0
    engagement_rate = round(100 * engagements / impressions, 1) if impressions else None

    for campaign in campaigns:
        campaign_tasks = campaign.tasks.all()
        total = campaign_tasks.count()
        completed = campaign_tasks.filter(status="done").count()
        campaign.dashboard_progress = round(100 * completed / total) if total else 0
        campaign.dashboard_health = min(100, 70 + campaign.plan_revision * 8)
        campaign.dashboard_next = (
            campaign.items.filter(planned_on__gte=timezone.localdate())
            .order_by("planned_on")
            .first()
        )

    channel_rows = []
    for row in (
        observations.values("channel")
        .annotate(impressions=Sum("impressions"), engagements=Sum("engagements"))
        .order_by("channel")
    ):
        row["rate"] = (
            round(100 * (row["engagements"] or 0) / row["impressions"], 1)
            if row["impressions"]
            else None
        )
        channel_rows.append(row)
    max_rate = max((row["rate"] or 0 for row in channel_rows), default=0)
    for row in channel_rows:
        row["bar_width"] = round(100 * (row["rate"] or 0) / max_rate) if max_rate else 0

    latest_insight = Insight.objects.filter(campaign_id__in=campaign_ids).order_by("-created_at").first()
    latest_recommendation = (
        Recommendation.objects.filter(campaign_id__in=campaign_ids, status="proposed")
        .order_by("-created_at")
        .first()
    )
    context = {
        "membership": membership,
        "campaigns": campaigns,
        "dashboard_metrics": {
            "active_campaigns": sum(c.status == "active" for c in campaigns),
            "task_completion": round(100 * task_done / task_total) if task_total else 0,
            "content_count": ContentItem.objects.filter(campaign_id__in=campaign_ids).count(),
            "engagement_rate": engagement_rate,
        },
        "my_tasks": tasks.exclude(status__in=["done", "cancelled"]).order_by("due_on")[:4],
        "upcoming_items": ContentItem.objects.filter(
            campaign_id__in=campaign_ids, planned_on__gte=timezone.localdate()
        ).order_by("planned_on")[:3],
        "recent_activity": AuditEvent.objects.filter(organization=organization)
        .select_related("actor", "campaign")
        .order_by("-created_at")[:4],
        "channel_performance": channel_rows,
        "latest_insight": latest_insight,
        "latest_recommendation": latest_recommendation,
    }
    return render(request, "dashboard.html", context)


@login_required
def campaign_create(request):
    membership = membership_for(request.user)
    if not membership or membership.role not in ("owner", "manager"):
        raise PermissionDenied
    form = CampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        campaign = services.create_campaign(request.user, form.cleaned_data)
        return redirect("campaign_detail", pk=campaign.pk)
    return render(request, "campaign_form.html", {"form": form})


@login_required
def campaign_edit(request, pk):
    campaign = campaign_for(request.user, pk)
    if not can_manage(request.user, campaign):
        raise PermissionDenied
    form = CampaignForm(request.POST or None, instance=campaign)
    if request.method == "POST" and form.is_valid():
        try:
            services.update_campaign(request.user, campaign, form.cleaned_data)
            messages.success(request, "Brief updated.")
            return redirect("campaign_detail", pk=pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "campaign_form.html", {"form": form, "campaign": campaign})


@login_required
def strategy_edit(request, pk):
    campaign = campaign_for(request.user, pk)
    if not can_manage(request.user, campaign):
        raise PermissionDenied
    strategy = (
        Strategy.objects.filter(campaign=campaign, status="draft").order_by("-revision").first()
    )
    if not strategy:
        messages.error(request, "No draft strategy is available.")
        return redirect("campaign_detail", pk=pk)
    initial = {key: strategy.data.get(key, "") for key in ("objective", "audience", "key_message")}
    initial["pillars"] = "\n".join(strategy.data.get("pillars", []))
    form = StrategyEditForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            services.update_strategy(request.user, campaign, strategy, form.cleaned_data)
            messages.success(request, "Strategy draft updated.")
            return redirect("campaign_detail", pk=pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "strategy_form.html", {"form": form, "campaign": campaign})


@login_required
def campaign_detail(request, pk):
    campaign = campaign_for(request.user, pk)
    strategy = campaign.strategies.order_by("-revision").first()
    proposal = (
        PlanProposal.objects.filter(campaign=campaign, status="draft")
        .order_by("-created_at")
        .first()
    )
    insight = Insight.objects.filter(campaign=campaign).order_by("-created_at").first()
    recommendation = (
        Recommendation.objects.filter(campaign=campaign, status="proposed")
        .order_by("-created_at")
        .first()
    )
    evidence, _ = evidence_for(campaign)
    return render(
        request,
        "campaign_detail.html",
        {
            "campaign": campaign,
            "strategy": strategy,
            "proposal": proposal,
            "items": campaign.items.order_by("planned_on"),
            "tasks": campaign.tasks.order_by("due_on"),
            "observations": campaign.observations.order_by("-observed_on"),
            "observation_form": ObservationForm(),
            "insight": insight,
            "recommendation": recommendation,
            "evidence": evidence,
            "can_manage": can_manage(request.user, campaign),
        },
    )


def action(request, pk, operation):
    guard = post_only(request)
    if guard:
        return guard
    campaign = campaign_for(request.user, pk)
    try:
        operation(request.user, campaign)
        messages.success(request, "Saved successfully.")
    except (ValidationError, AIError) as exc:
        messages.error(request, exc.messages[0] if isinstance(exc, ValidationError) else str(exc))
    return redirect("campaign_detail", pk=pk)


@login_required
def strategy_generate(request, pk):
    return action(request, pk, services.generate_strategy)


@login_required
def strategy_approve(request, pk):
    return action(request, pk, services.approve_strategy)


@login_required
def plan_generate(request, pk):
    return action(request, pk, services.generate_plan)


@login_required
def plan_apply(request, pk):
    return action(request, pk, services.apply_plan)


@login_required
def insight_generate(request, pk):
    return action(request, pk, services.generate_insight)


@login_required
def recommendation_apply(request, pk):
    return action(request, pk, services.apply_recommendation)


@login_required
def content_generate(request, pk, item_pk):
    guard = post_only(request)
    if guard:
        return guard
    campaign = campaign_for(request.user, pk)
    item = get_object_or_404(ContentItem, campaign=campaign, pk=item_pk)
    try:
        services.generate_content(request.user, campaign, item)
        messages.success(request, "Content draft generated.")
    except (ValidationError, AIError) as exc:
        messages.error(request, exc.messages[0] if isinstance(exc, ValidationError) else str(exc))
    return redirect("campaign_detail", pk=pk)


@login_required
def content_edit(request, pk, item_pk):
    campaign = campaign_for(request.user, pk)
    if not can_manage(request.user, campaign):
        raise PermissionDenied
    item = get_object_or_404(ContentItem, campaign=campaign, pk=item_pk)
    form = ContentItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        try:
            services.update_content(request.user, campaign, item, form.cleaned_data)
            messages.success(request, "Content item updated.")
            return redirect("campaign_detail", pk=pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "content_form.html", {"form": form, "campaign": campaign, "item": item})


@login_required
def observation_add(request, pk):
    guard = post_only(request)
    if guard:
        return guard
    campaign = campaign_for(request.user, pk)
    if not can_manage(request.user, campaign):
        raise PermissionDenied
    form = ObservationForm(request.POST)
    if form.is_valid():
        try:
            services.add_observation(request.user, campaign, form.cleaned_data)
            messages.success(request, "Performance observation saved.")
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    else:
        messages.error(request, "Check performance fields: " + str(form.errors.as_text()))
    return redirect("campaign_detail", pk=pk)


@login_required
def report(request, pk):
    campaign = campaign_for(request.user, pk)
    evidence, _ = evidence_for(campaign)
    insight = Insight.objects.filter(campaign=campaign).order_by("-created_at").first()
    return render(
        request,
        "report.html",
        {
            "campaign": campaign,
            "evidence": evidence,
            "insight": insight,
            "items": campaign.items.order_by("planned_on"),
        },
    )


@login_required
def campaign_summary(request, pk):
    campaign = campaign_for(request.user, pk)
    evidence, _ = evidence_for(campaign)
    return render(request, "partials/summary.html", {"campaign": campaign, "evidence": evidence})
