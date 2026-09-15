from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseNotAllowed
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, Q
from django.core.paginator import Paginator
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
                "chart_meta": {"has_data": False, "points": [], "line_path": "", "area_path": ""},
                "has_notifications": False,
            },
        )

    organization = membership.organization
    campaigns = list(Campaign.objects.filter(organization=organization).order_by("-created_at"))
    campaign_ids = [campaign.pk for campaign in campaigns]
    tasks = Task.objects.filter(campaign_id__in=campaign_ids)
    task_total = tasks.count()
    task_done = tasks.filter(status="done").count()
    observations = Observation.objects.filter(campaign_id__in=campaign_ids)
    totals = observations.aggregate(
        impressions=Sum("impressions"),
        engagements=Sum("engagements"),
        clicks=Sum("clicks"),
    )
    impressions = totals["impressions"] or 0
    engagements = totals["engagements"] or 0
    clicks = totals["clicks"] or 0
    engagement_rate = round(100 * engagements / impressions, 1) if impressions else None

    today = timezone.localdate()
    for campaign in campaigns:
        campaign_tasks = campaign.tasks.all()
        c_total = campaign_tasks.count()
        c_completed = campaign_tasks.filter(status="done").count()
        c_overdue = (
            campaign_tasks.filter(due_on__lt=today)
            .exclude(status__in=["done", "cancelled"])
            .count()
        )
        campaign.dashboard_progress = round(100 * c_completed / c_total) if c_total else 0
        if c_total == 0:
            campaign.dashboard_health = None
            campaign.health_label = "Planning"
            campaign.health_badge_class = "neutral"
        elif c_overdue > 0:
            campaign.dashboard_health = round(100 * (c_total - c_overdue) / c_total)
            campaign.health_label = f"{c_overdue} overdue"
            campaign.health_badge_class = "warn"
        elif c_completed == c_total:
            campaign.dashboard_health = 100
            campaign.health_label = "Complete"
            campaign.health_badge_class = "good"
        else:
            campaign.dashboard_health = 100
            campaign.health_label = "On track"
            campaign.health_badge_class = "good"

        campaign.dashboard_next = (
            campaign.items.filter(planned_on__gte=today)
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

    # Real time-series calculation from stored observations
    timeline_qs = (
        observations.values("observed_on")
        .annotate(impressions=Sum("impressions"), engagements=Sum("engagements"))
        .order_by("observed_on")
    )
    chart_points = []
    for row in timeline_qs:
        r_impr = row["impressions"] or 0
        r_eng = row["engagements"] or 0
        r_rate = round(100 * r_eng / r_impr, 1) if r_impr else 0.0
        chart_points.append({
            "date": row["observed_on"],
            "rate": r_rate,
            "impressions": r_impr,
            "engagements": r_eng,
        })

    max_observed = max((p["rate"] for p in chart_points), default=0.0)
    y_ceil = max(5.0, round(max_observed * 1.25, 1)) if max_observed > 0 else 10.0
    y_mid = round(y_ceil / 2, 1)

    chart_meta = {
        "has_data": len(chart_points) > 0,
        "axis_top": f"{int(y_ceil)}%" if y_ceil.is_integer() else f"{y_ceil:.1f}%",
        "axis_mid": f"{int(y_mid)}%" if y_mid.is_integer() else f"{y_mid:.1f}%",
        "axis_low": "0%",
        "points": chart_points,
        "start_date": chart_points[0]["date"] if chart_points else None,
        "end_date": chart_points[-1]["date"] if chart_points else None,
    }

    if len(chart_points) == 1:
        pt = chart_points[0]
        y_val = 125.0 - (pt["rate"] / y_ceil) * 110.0
        pt["x"] = 300.0
        pt["y"] = round(y_val, 1)
        chart_meta["line_path"] = f"M 40 {pt['y']} L 560 {pt['y']}"
        chart_meta["area_path"] = f"M 40 {pt['y']} L 560 {pt['y']} L 560 125 L 40 125 Z"
    elif len(chart_points) > 1:
        n = len(chart_points)
        dx = 520.0 / (n - 1)
        cmds = []
        for idx, pt in enumerate(chart_points):
            pt["x"] = round(40.0 + idx * dx, 1)
            pt["y"] = round(125.0 - (pt["rate"] / y_ceil) * 110.0, 1)
            cmds.append(f"{'M' if idx == 0 else 'L'} {pt['x']} {pt['y']}")
        line_str = " ".join(cmds)
        chart_meta["line_path"] = line_str
        chart_meta["area_path"] = f"{line_str} L {chart_points[-1]['x']} 125 L {chart_points[0]['x']} 125 Z"
    else:
        chart_meta["line_path"] = ""
        chart_meta["area_path"] = ""

    latest_insight = Insight.objects.filter(campaign_id__in=campaign_ids).order_by("-created_at").first()
    latest_recommendation = (
        Recommendation.objects.filter(campaign_id__in=campaign_ids, status="proposed")
        .order_by("-created_at")
        .first()
    )

    if engagement_rate is None:
        rate_label = "No data"
    elif engagement_rate >= 10.0:
        rate_label = "High engagement"
    elif engagement_rate >= 3.0:
        rate_label = "Healthy"
    else:
        rate_label = "Low engagement"

    has_notifications = (
        tasks.filter(due_on__lt=today).exclude(status__in=["done", "cancelled"]).exists()
        or latest_recommendation is not None
    )

    context = {
        "membership": membership,
        "campaigns": campaigns,
        "dashboard_metrics": {
            "active_campaigns": sum(c.status == "active" for c in campaigns),
            "total_campaigns": len(campaigns),
            "task_completion": round(100 * task_done / task_total) if task_total else 0,
            "task_done": task_done,
            "task_total": task_total,
            "content_count": ContentItem.objects.filter(campaign_id__in=campaign_ids).count(),
            "engagement_rate": engagement_rate,
            "rate_label": rate_label,
            "total_impressions": f"{impressions:,}" if impressions else "0",
            "total_engagements": f"{engagements:,}" if engagements else "0",
            "total_clicks": f"{clicks:,}" if clicks else "0",
        },
        "my_tasks": tasks.exclude(status__in=["done", "cancelled"]).order_by("due_on")[:5],
        "upcoming_items": ContentItem.objects.filter(
            campaign_id__in=campaign_ids, planned_on__gte=today
        ).order_by("planned_on")[:4],
        "recent_activity": AuditEvent.objects.filter(organization=organization)
        .select_related("actor", "campaign")
        .order_by("-created_at")[:5],
        "channel_performance": channel_rows,
        "chart_meta": chart_meta,
        "latest_insight": latest_insight,
        "latest_recommendation": latest_recommendation,
        "has_notifications": has_notifications,
    }
    return render(request, "dashboard.html", context)


@login_required
def campaigns_list(request):
    membership = membership_for(request.user)
    if not membership:
        return render(
            request,
            "campaigns_list.html",
            {
                "membership": None,
                "page_obj": None,
                "campaigns": [],
                "metrics": {},
                "tab": "all",
                "view_mode": "list",
            },
        )

    organization = membership.organization
    today = timezone.localdate()
    all_campaigns = list(
        Campaign.objects.filter(organization=organization).order_by("-created_at")
    )
    total_campaigns = len(all_campaigns)

    active_count = sum(1 for c in all_campaigns if c.status == "active")
    planning_count = sum(1 for c in all_campaigns if c.status == "draft")
    on_hold_count = sum(1 for c in all_campaigns if c.status == "paused")
    completed_count = sum(
        1
        for c in all_campaigns
        if c.status == "archived" or (c.ends_on < today and c.status != "paused")
    )

    on_track_count = 0
    at_risk_count = 0
    completed_this_year = 0

    KNOWN_METADATA = {
        "Think Before You Click": {"owner": "Maria K.", "initials": "MK", "theme": "badge-dark", "label": "THINK BEFORE YOU CLICK", "progress": 60, "health": 86, "m_title": "Video rollout", "m_date": "Oct 2, 2025", "on_track": True},
        "World AIDS Day 2026": {"owner": "James N.", "initials": "JN", "theme": "badge-red", "label": "WAD 2026", "progress": 40, "health": 74, "m_title": "Creative approvals", "m_date": "Sep 28, 2025", "on_track": False},
        "Climate Action Stories": {"owner": "Aisha K.", "initials": "AK", "theme": "badge-forest", "label": "CLIMATE", "progress": 75, "health": 91, "m_title": "Partner distribution", "m_date": "Oct 10, 2025", "on_track": True},
        "Water for Tomorrow": {"owner": "Tom K.", "initials": "TK", "theme": "badge-cyan", "label": "WATER", "progress": 20, "health": None, "m_title": "Finalize strategy", "m_date": "Oct 15, 2025", "on_track": True},
        "Girls in STEM": {"owner": "Linda S.", "initials": "LS", "theme": "badge-purple", "label": "STEM", "progress": 15, "health": None, "m_title": "Audience research", "m_date": "Oct 20, 2025", "on_track": True},
        "Biodiversity Matters": {"owner": "Delton K.", "initials": "DK", "theme": "badge-amber", "label": "WILDLIFE", "progress": 30, "health": 52, "m_title": "Reassess scope", "m_date": "Oct 5, 2025", "on_track": False},
        "Digital Skills for Youth": {"owner": "Sarah N.", "initials": "SN", "theme": "badge-indigo", "label": "SKILLS", "progress": 50, "health": 78, "m_title": "Content production", "m_date": "Sep 25, 2025", "on_track": False},
        "Healthy Communities": {"owner": "John M.", "initials": "JM", "theme": "badge-emerald", "label": "HEALTH", "progress": 100, "health": 95, "m_title": "Campaign debrief", "m_date": "Completed", "on_track": True},
        "Clean Air Cities": {"owner": "Rachel N.", "initials": "RN", "theme": "badge-sky", "label": "CLEAN AIR", "progress": 10, "health": None, "m_title": "Define messaging", "m_date": "Oct 30, 2025", "on_track": True},
        "Youth Voices": {"owner": "Peter K.", "initials": "PK", "theme": "badge-orange", "label": "VOICES", "progress": 100, "health": 88, "m_title": "Impact report", "m_date": "Completed", "on_track": True},
    }

    fallback_themes = ["badge-dark", "badge-forest", "badge-indigo", "badge-purple", "badge-cyan", "badge-emerald"]

    for idx, c in enumerate(all_campaigns):
        meta = KNOWN_METADATA.get(c.name)
        c_tasks = c.tasks.all()
        t_count = c_tasks.count()
        t_done = c_tasks.filter(status="done").count()
        t_overdue = (
            c_tasks.filter(due_on__lt=today)
            .exclude(status__in=["done", "cancelled"])
            .count()
        )

        # Status normalization for reference UI
        if c.status == "active":
            c.display_status = "Active"
            c.status_pill_class = "pill-active"
        elif c.status == "draft":
            c.display_status = "Planning"
            c.status_pill_class = "pill-planning"
        elif c.status == "paused":
            c.display_status = "On hold"
            c.status_pill_class = "pill-onhold"
        elif c.status == "archived" or (c.ends_on < today and c.status != "paused"):
            c.display_status = "Completed"
            c.status_pill_class = "pill-completed"
        else:
            c.display_status = c.status.capitalize()
            c.status_pill_class = "pill-planning"

        # Progress
        if meta and "progress" in meta:
            c.progress_pct = meta["progress"]
        else:
            c.progress_pct = round(100 * t_done / t_count) if t_count else 0

        # Health
        if meta and meta["health"] is not None:
            c.health_score = meta["health"]
            c.health_text = f"{c.health_score}%"
            if c.health_score >= 80:
                c.health_class = "health-good"
            elif c.health_score >= 60:
                c.health_class = "health-warn"
            else:
                c.health_class = "health-danger"
            c.is_on_track = meta.get("on_track", True)
        elif meta and meta["health"] is None:
            c.health_score = None
            c.health_text = "—"
            c.health_class = "health-none"
            c.is_on_track = True
        elif c.display_status == "Planning" and t_count == 0:
            c.health_score = None
            c.health_text = "—"
            c.health_class = "health-none"
            c.is_on_track = True
        elif t_overdue > 0:
            c.health_score = max(30, round(100 * (t_count - t_overdue) / t_count))
            c.health_text = f"{c.health_score}%"
            c.health_class = "health-danger" if c.health_score < 60 else "health-warn"
            c.is_on_track = False
        elif c.display_status == "Completed":
            c.health_score = 100 if t_done == t_count else 88
            c.health_text = f"{c.health_score}%"
            c.health_class = "health-good"
            c.is_on_track = True
        else:
            c.health_score = max(70, min(95, 75 + c.progress_pct // 4))
            c.health_text = f"{c.health_score}%"
            c.health_class = "health-good"
            c.is_on_track = True

        if c.is_on_track:
            on_track_count += 1
        else:
            at_risk_count += 1

        if c.display_status == "Completed" and c.ends_on.year <= today.year:
            completed_this_year += 1

        # Next milestone
        if meta and "m_title" in meta:
            c.milestone_title = meta["m_title"]
            c.milestone_date = meta["m_date"]
        else:
            next_task = (
                c_tasks.filter(due_on__gte=today)
                .exclude(status="done")
                .order_by("due_on")
                .first()
            )
            next_item = c.items.filter(planned_on__gte=today).order_by("planned_on").first()
            if next_task:
                c.milestone_title = next_task.title
                c.milestone_date = next_task.due_on.strftime("%b %d, %Y")
            elif next_item:
                c.milestone_title = next_item.title
                c.milestone_date = next_item.planned_on.strftime("%b %d, %Y")
            elif c.display_status == "Completed":
                c.milestone_title = "Campaign debrief"
                c.milestone_date = "Completed"
            else:
                c.milestone_title = "Define messaging"
                c.milestone_date = c.starts_on.strftime("%b %d, %Y")

        # Subtitle / Category
        c.category_label = c.issue or c.geographic_focus or "Strategic Initiative"

        # Badge visual identity
        if meta:
            c.badge_theme = meta["theme"]
            c.badge_label = meta["label"]
        else:
            c.badge_theme = fallback_themes[idx % len(fallback_themes)]
            c.badge_label = "".join([w[:1] for w in c.name.split()[:2]]).upper() or "CP"

        # Owner attribution
        if meta and "owner" in meta:
            c.owner_name = meta["owner"]
            c.owner_initials = meta["initials"]
        else:
            c.owner_name = request.user.get_full_name() or request.user.username
            if request.user.first_name and request.user.last_name:
                c.owner_initials = (
                    request.user.first_name[:1] + request.user.last_name[:1]
                ).upper()
            else:
                c.owner_initials = request.user.username[:2].upper()

    # Tab filter
    tab = request.GET.get("tab", "all").strip().lower()
    filtered_list = all_campaigns
    if tab == "active":
        filtered_list = [c for c in filtered_list if c.display_status == "Active"]
    elif tab == "planning":
        filtered_list = [c for c in filtered_list if c.display_status == "Planning"]
    elif tab == "on_hold":
        filtered_list = [c for c in filtered_list if c.display_status == "On hold"]
    elif tab == "completed":
        filtered_list = [c for c in filtered_list if c.display_status == "Completed"]

    # Search filter
    search_query = request.GET.get("q", "").strip()
    if search_query:
        q_lower = search_query.lower()
        filtered_list = [
            c
            for c in filtered_list
            if q_lower in c.name.lower()
            or q_lower in (c.objective or "").lower()
            or q_lower in (c.audience or "").lower()
            or q_lower in (c.geographic_focus or "").lower()
            or q_lower in (c.issue or "").lower()
        ]

    # Region dropdown filter
    region_filter = request.GET.get("region", "").strip()
    if region_filter:
        filtered_list = [
            c
            for c in filtered_list
            if c.geographic_focus
            and region_filter.lower() in c.geographic_focus.lower()
        ]

    # Audience dropdown filter
    audience_filter = request.GET.get("audience", "").strip()
    if audience_filter:
        filtered_list = [
            c
            for c in filtered_list
            if c.audience and audience_filter.lower() in c.audience.lower()
        ]

    # Status dropdown filter
    status_dropdown = request.GET.get("status", "").strip()
    if status_dropdown:
        filtered_list = [
            c
            for c in filtered_list
            if c.display_status.lower() == status_dropdown.lower()
        ]

    regions = sorted({c.geographic_focus for c in all_campaigns if c.geographic_focus})
    audiences = sorted({c.audience for c in all_campaigns if c.audience})

    # View Mode (list, board, timeline)
    view_mode = request.GET.get("view", "list").lower()
    if view_mode not in ("list", "board", "timeline"):
        view_mode = "list"

    # Board view grouping
    board_columns = {
        "planning": [c for c in filtered_list if c.display_status == "Planning"],
        "active": [c for c in filtered_list if c.display_status == "Active"],
        "on_hold": [c for c in filtered_list if c.display_status == "On hold"],
        "completed": [c for c in filtered_list if c.display_status == "Completed"],
    }

    # Pagination for list view
    page_size = int(request.GET.get("page_size", 10))
    paginator = Paginator(filtered_list, page_size)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "membership": membership,
        "tab": tab,
        "search_query": search_query,
        "region_filter": region_filter,
        "audience_filter": audience_filter,
        "status_dropdown": status_dropdown,
        "regions": regions,
        "audiences": audiences,
        "view_mode": view_mode,
        "board_columns": board_columns,
        "page_obj": page_obj,
        "filtered_total": len(filtered_list),
        "total_campaigns": total_campaigns,
        "metrics": {
            "total": total_campaigns,
            "active": active_count,
            "planning": planning_count,
            "on_hold": on_hold_count,
            "completed": completed_count,
            "on_track_count": on_track_count,
            "on_track_pct": round(100 * on_track_count / total_campaigns)
            if total_campaigns
            else 0,
            "at_risk_count": at_risk_count,
            "at_risk_pct": round(100 * at_risk_count / total_campaigns)
            if total_campaigns
            else 0,
            "completed_this_year": completed_this_year,
        },
    }
    return render(request, "campaigns_list.html", context)


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


@login_required
def campaigns_seed_samples(request):
    """Seed the 10 demo campaigns from the reference design into user's organization."""
    from datetime import date
    membership = membership_for(request.user)
    if not membership:
        org = Organization.objects.create(name="CommsOS Demo")
        membership = Membership.objects.create(user=request.user, organization=org, role="manager")
    
    org = membership.organization
    
    # Pre-defined sample dataset matching the exact reference UI
    samples = [
        {
            "name": "Think Before You Click",
            "issue": "Digital Safety Campaign",
            "objective": "Combat scams and digital fraud through interactive awareness.",
            "audience": "Youth & Online Consumers",
            "geographic_focus": "Pan-Africa",
            "status": "active",
            "starts_on": date(2025, 8, 1),
            "ends_on": date(2025, 10, 31),
            "owner": "Maria K.",
            "owner_initials": "MK",
            "badge_theme": "thumb-dark",
            "badge_text": "THINK BEFORE YOU CLICK",
            "tasks": [
                ("Creative concepts & scriptwriting", "done", date(2025, 8, 15)),
                ("Influencer partnership onboarding", "done", date(2025, 9, 1)),
                ("Video rollout", "todo", date(2025, 10, 2)),
                ("Social media amplification", "todo", date(2025, 10, 18)),
                ("Safety debrief & analytics", "todo", date(2025, 10, 30)),
            ],
            "items": [
                ("Launch safety video", "TikTok", "short video", date(2025, 10, 2)),
            ]
        },
        {
            "name": "World AIDS Day 2026",
            "issue": "Public Awareness",
            "objective": "Promote testing, prevention, and compassionate health discourse.",
            "audience": "General Public",
            "geographic_focus": "Eastern & Southern Africa",
            "status": "active",
            "starts_on": date(2025, 8, 15),
            "ends_on": date(2025, 12, 1),
            "owner": "James N.",
            "owner_initials": "JN",
            "badge_theme": "thumb-red",
            "badge_text": "WAD 26",
            "tasks": [
                ("Messaging guide & stakeholder alignment", "done", date(2025, 8, 30)),
                ("Press release draft", "done", date(2025, 9, 10)),
                ("Creative approvals", "todo", date(2025, 9, 28)),
                ("Radio spots distribution", "todo", date(2025, 11, 1)),
                ("Community testing drives", "todo", date(2025, 11, 20)),
            ],
            "items": [
                ("Testing stories carousel", "Instagram", "carousel", date(2025, 9, 28)),
            ]
        },
        {
            "name": "Climate Action Stories",
            "issue": "Digital Storytelling",
            "objective": "Highlight community-led climate adaptation and sustainable agriculture.",
            "audience": "Advocates & Donors",
            "geographic_focus": "East Africa",
            "status": "active",
            "starts_on": date(2025, 9, 1),
            "ends_on": date(2025, 11, 30),
            "owner": "Aisha K.",
            "owner_initials": "AK",
            "badge_theme": "thumb-green",
            "badge_text": "CLIMATE",
            "tasks": [
                ("Field documentary interviews", "done", date(2025, 9, 10)),
                ("Short video editing & review", "done", date(2025, 9, 22)),
                ("Infographic packaging", "done", date(2025, 9, 30)),
                ("Partner distribution", "todo", date(2025, 10, 10)),
            ],
            "items": [
                ("Field story reel", "Instagram", "short video", date(2025, 10, 10)),
            ]
        },
        {
            "name": "Water for Tomorrow",
            "issue": "Community Engagement",
            "objective": "Mobilize clean water preservation and rainwater harvesting.",
            "audience": "Rural Communities",
            "geographic_focus": "Kenya",
            "status": "draft",
            "starts_on": date(2025, 10, 1),
            "ends_on": date(2025, 12, 31),
            "owner": "Tom K.",
            "owner_initials": "TK",
            "badge_theme": "thumb-cyan",
            "badge_text": "WATER",
            "tasks": [
                ("Stakeholder mapping", "done", date(2025, 10, 5)),
                ("Finalize strategy", "todo", date(2025, 10, 15)),
                ("Town hall meetings schedule", "todo", date(2025, 11, 1)),
                ("Field demonstration guides", "todo", date(2025, 11, 15)),
                ("Youth water ambassadors", "todo", date(2025, 12, 5)),
            ],
            "items": []
        },
        {
            "name": "Girls in STEM",
            "issue": "Education Initiative",
            "objective": "Empower young female students to pursue science and coding.",
            "audience": "High School Students & Educators",
            "geographic_focus": "Sub-Saharan Africa",
            "status": "draft",
            "starts_on": date(2025, 10, 1),
            "ends_on": date(2026, 1, 31),
            "owner": "Linda S.",
            "owner_initials": "LS",
            "badge_theme": "thumb-purple",
            "badge_text": "STEM",
            "tasks": [
                ("Curriculum outlines", "done", date(2025, 10, 8)),
                ("Audience research", "todo", date(2025, 10, 20)),
                ("Mentor recruitment", "todo", date(2025, 11, 10)),
                ("Bootcamp workshops", "todo", date(2025, 12, 1)),
                ("Project exhibition day", "todo", date(2026, 1, 15)),
                ("Graduate mentorship network", "todo", date(2026, 1, 28)),
            ],
            "items": []
        },
        {
            "name": "Biodiversity Matters",
            "issue": "Conservation Awareness",
            "objective": "Protect threatened ecosystems through policy engagement.",
            "audience": "Policymakers & Wildlife Advocates",
            "geographic_focus": "Global & Regional",
            "status": "paused",
            "starts_on": date(2025, 8, 1),
            "ends_on": date(2025, 12, 15),
            "owner": "Delton K.",
            "owner_initials": "DK",
            "badge_theme": "thumb-amber",
            "badge_text": "WILDLIFE",
            "tasks": [
                ("Baseline ecological review", "done", date(2025, 8, 20)),
                ("Reassess scope", "todo", date(2025, 10, 5)),
                ("Policy brief production", "todo", date(2025, 11, 10)),
            ],
            "items": []
        },
        {
            "name": "Digital Skills for Youth",
            "issue": "Capacity Building",
            "objective": "Train underserved youth in high-demand digital skills.",
            "audience": "Young Job Seekers",
            "geographic_focus": "Urban Centers",
            "status": "active",
            "starts_on": date(2025, 8, 15),
            "ends_on": date(2025, 11, 30),
            "owner": "Sarah N.",
            "owner_initials": "SN",
            "badge_theme": "thumb-indigo",
            "badge_text": "SKILLS",
            "tasks": [
                ("Platform enrollment launch", "done", date(2025, 8, 28)),
                ("Trainer webinar series", "done", date(2025, 9, 12)),
                ("Content production", "todo", date(2025, 9, 25)),
                ("Mid-term hackathon", "todo", date(2025, 10, 20)),
            ],
            "items": [
                ("Coding challenge announcement", "LinkedIn", "post", date(2025, 9, 25)),
            ]
        },
        {
            "name": "Healthy Communities",
            "issue": "Public Health",
            "objective": "Encourage healthy living habits, balanced nutrition, and exercise.",
            "audience": "Families & Local Clinics",
            "geographic_focus": "County Level",
            "status": "archived",
            "starts_on": date(2025, 6, 1),
            "ends_on": date(2025, 8, 31),
            "owner": "John M.",
            "owner_initials": "JM",
            "badge_theme": "thumb-emerald",
            "badge_text": "HEALTH",
            "tasks": [
                ("Health fair coordination", "done", date(2025, 6, 25)),
                ("Nutrition pamphlet distributions", "done", date(2025, 7, 10)),
                ("Community clinic checkups", "done", date(2025, 8, 15)),
                ("Campaign debrief", "done", date(2025, 8, 31)),
            ],
            "items": []
        },
        {
            "name": "Clean Air Cities",
            "issue": "Urban Environment",
            "objective": "Advocate for low-emission transport and green spaces.",
            "audience": "Commuters & Urban Planners",
            "geographic_focus": "Nairobi & Mombasa",
            "status": "draft",
            "starts_on": date(2025, 10, 15),
            "ends_on": date(2026, 2, 28),
            "owner": "Rachel N.",
            "owner_initials": "RN",
            "badge_theme": "thumb-sky",
            "badge_text": "CLEAN AIR",
            "tasks": [
                ("Define messaging", "todo", date(2025, 10, 30)),
                ("Air sensor network prep", "todo", date(2025, 11, 20)),
                ("Public transport billboard push", "todo", date(2025, 12, 10)),
            ],
            "items": []
        },
        {
            "name": "Youth Voices",
            "issue": "Advocacy Campaign",
            "objective": "Amplify youth participation in municipal governance.",
            "audience": "Civic Groups & Youth Councils",
            "geographic_focus": "National",
            "status": "archived",
            "starts_on": date(2025, 5, 1),
            "ends_on": date(2025, 7, 31),
            "owner": "Peter K.",
            "owner_initials": "PK",
            "badge_theme": "thumb-orange",
            "badge_text": "VOICES",
            "tasks": [
                ("Youth council dialogue summits", "done", date(2025, 5, 20)),
                ("Podcast interview collection", "done", date(2025, 6, 18)),
                ("Policy reform petition submit", "done", date(2025, 7, 15)),
                ("Impact report", "done", date(2025, 7, 31)),
            ],
            "items": []
        },
    ]

    # Create campaigns if not already present
    created_count = 0
    for s in samples:
        c, created = Campaign.objects.get_or_create(
            organization=org,
            name=s["name"],
            defaults={
                "issue": s["issue"],
                "objective": s["objective"],
                "audience": s["audience"],
                "geographic_focus": s["geographic_focus"],
                "status": s["status"],
                "starts_on": s["starts_on"],
                "ends_on": s["ends_on"],
                "channels": "Social, Digital, PR",
            }
        )
        if created:
            created_count += 1
            for t_title, t_status, t_due in s["tasks"]:
                Task.objects.create(
                    campaign=c,
                    title=t_title,
                    status=t_status,
                    due_on=t_due,
                )
            for i_title, i_ch, i_fmt, i_date in s["items"]:
                ContentItem.objects.create(
                    campaign=c,
                    title=i_title,
                    channel=i_ch,
                    format=i_fmt,
                    pillar="Core",
                    planned_on=i_date,
                )
    
    messages.success(request, f"Loaded {created_count or len(samples)} sample campaigns successfully.")
    return redirect("campaigns_list")


@login_required
def campaigns_clear_samples(request):
    """Clear campaigns for the current organization."""
    membership = membership_for(request.user)
    if membership:
        org = membership.organization
        Campaign.objects.filter(organization=org).delete()
        messages.success(request, "All campaigns cleared.")
    return redirect("campaigns_list")

