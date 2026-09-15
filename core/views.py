import calendar
from datetime import datetime, date, time, timedelta
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
    Observation,
    AuditEvent,
    CalendarEvent,
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

    palette_themes = [
        "badge-dark", "badge-forest", "badge-indigo", "badge-purple",
        "badge-cyan", "badge-emerald", "badge-amber", "badge-sky", "badge-orange", "badge-red"
    ]

    for idx, c in enumerate(all_campaigns):
        c_tasks = c.tasks.all()
        t_count = c_tasks.count()
        t_done = c_tasks.filter(status="done").count()
        t_overdue = (
            c_tasks.filter(due_on__lt=today)
            .exclude(status__in=["done", "cancelled"])
            .count()
        )

        # Status normalization
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

        # Dynamic progress calculation from tasks
        c.progress_pct = round(100 * t_done / t_count) if t_count else 0

        # Dynamic health evaluation
        if c.display_status == "Planning" and t_count == 0:
            c.health_score = None
            c.health_text = "—"
            c.health_class = "health-none"
            c.is_on_track = True
        elif t_overdue > 0:
            c.health_score = max(20, round(100 * (t_count - t_overdue) / t_count))
            c.health_text = f"{c.health_score}%"
            c.health_class = "health-danger" if c.health_score < 60 else "health-warn"
            c.is_on_track = False
        elif c.display_status == "Completed":
            c.health_score = 100 if (t_count and t_done == t_count) else (90 if t_count else 100)
            c.health_text = f"{c.health_score}%"
            c.health_class = "health-good"
            c.is_on_track = True
        else:
            c.health_score = max(70, min(95, 75 + c.progress_pct // 4)) if t_count else 85
            c.health_text = f"{c.health_score}%"
            c.health_class = "health-good"
            c.is_on_track = True

        if c.is_on_track:
            on_track_count += 1
        else:
            at_risk_count += 1

        if c.display_status == "Completed" and c.ends_on.year <= today.year:
            completed_this_year += 1

        # Dynamic next milestone from actual tasks or content items
        next_task = (
            c_tasks.filter(due_on__gte=today)
            .exclude(status__in=["done", "cancelled"])
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
            c.milestone_title = "Completed"
            c.milestone_date = c.ends_on.strftime("%b %d, %Y")
        else:
            c.milestone_title = "Planning kickoff"
            c.milestone_date = c.starts_on.strftime("%b %d, %Y")

        # Subtitle / Category
        c.category_label = c.issue or c.geographic_focus or "Strategic Initiative"

        # Badge visual identity derived dynamically from campaign name initials
        words = [w for w in c.name.split() if w]
        if len(words) >= 2:
            c.badge_label = (words[0][:1] + words[1][:1]).upper()
        elif words:
            c.badge_label = words[0][:2].upper()
        else:
            c.badge_label = "CP"
        c.badge_theme = palette_themes[abs(hash(c.name)) % len(palette_themes)]
        c.badge_text = None

        # Owner attribution from creation audit event or organization member
        creation_event = AuditEvent.objects.filter(campaign=c, action__icontains="create").order_by("created_at").first()
        owner_user = creation_event.actor if (creation_event and creation_event.actor) else None
        if not owner_user:
            first_member = c.organization.memberships.select_related("user").first()
            owner_user = first_member.user if first_member else request.user

        name = owner_user.get_full_name() or owner_user.username
        c.owner_name = name
        parts = name.split()
        if len(parts) >= 2:
            c.owner_initials = (parts[0][:1] + parts[-1][:1]).upper()
        else:
            c.owner_initials = name[:2].upper()

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
def calendar_view(request):
    membership = membership_for(request.user)
    if not membership:
        return render(
            request,
            "calendar.html",
            {
                "membership": None,
                "week_days": [],
                "hours": [],
                "all_day_events": [],
                "day_columns": [],
                "mini_calendar": {},
                "upcoming_events": [],
                "date_range_label": "",
                "view_mode": "week",
            },
        )

    organization = membership.organization
    today = timezone.localdate()

    # Target date parsing
    date_param = request.GET.get("date", "").strip()
    try:
        target_date = datetime.strptime(date_param, "%Y-%m-%d").date() if date_param else today
    except (ValueError, TypeError):
        target_date = today

    view_mode = request.GET.get("view", "week").lower()
    if view_mode not in ("week", "month", "list", "timeline"):
        view_mode = "week"

    # Category filters
    active_types = request.GET.getlist("type")
    if not active_types:
        active_types = ["my_calendar", "campaigns", "content", "team", "external"]

    # Calculate Week window (Monday to Sunday)
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    prev_week_date = (start_of_week - timedelta(days=7)).strftime("%Y-%m-%d")
    next_week_date = (start_of_week + timedelta(days=7)).strftime("%Y-%m-%d")
    today_date_str = today.strftime("%Y-%m-%d")

    date_range_label = f"{start_of_week.strftime('%b %d')} – {end_of_week.strftime('%b %d, %Y')}"

    # Days list
    week_days = []
    for i in range(7):
        d = start_of_week + timedelta(days=i)
        week_days.append({
            "date": d,
            "date_str": d.strftime("%Y-%m-%d"),
            "day_name": d.strftime("%a"),
            "day_num": d.day,
            "month_name": d.strftime("%b"),
            "is_today": (d == today),
            "is_selected": (d == target_date),
            "col_index": i,
        })

    # Hours list (8 AM to 5 PM)
    hours = [
        {"val": 8, "label": "8 AM"},
        {"val": 9, "label": "9 AM"},
        {"val": 10, "label": "10 AM"},
        {"val": 11, "label": "11 AM"},
        {"val": 12, "label": "12 PM"},
        {"val": 13, "label": "1 PM"},
        {"val": 14, "label": "2 PM"},
        {"val": 15, "label": "3 PM"},
        {"val": 16, "label": "4 PM"},
        {"val": 17, "label": "5 PM"},
    ]

    # Fetch organization events, tasks, content items, and campaigns
    cal_events = list(CalendarEvent.objects.filter(
        organization=organization,
        date__range=(start_of_week, end_of_week),
        event_type__in=active_types,
    ).select_related("campaign", "created_by"))

    tasks = []
    if "campaigns" in active_types or "team" in active_types:
        tasks = list(Task.objects.filter(
            campaign__organization=organization,
            due_on__range=(start_of_week, end_of_week)
        ).select_related("campaign"))

    items = []
    if "content" in active_types:
        items = list(ContentItem.objects.filter(
            campaign__organization=organization,
            planned_on__range=(start_of_week, end_of_week)
        ).select_related("campaign"))

    campaigns = []
    if "campaigns" in active_types:
        campaigns = list(Campaign.objects.filter(
            organization=organization,
            starts_on__lte=end_of_week,
            ends_on__gte=start_of_week,
        ))

    # All-day banners
    all_day_events = []
    for c in campaigns:
        all_day_events.append({
            "title": f"{c.name} — Sprint",
            "campaign": c,
            "theme": "cal-banner-green",
            "icon": "flag",
            "starts_on": c.starts_on,
            "ends_on": c.ends_on,
        })
    for ce in cal_events:
        if ce.is_all_day:
            all_day_events.append({
                "title": ce.title,
                "campaign": ce.campaign,
                "theme": "cal-banner-purple",
                "icon": "flag",
                "starts_on": ce.date,
                "ends_on": ce.date,
            })

    # Hourly Grid Events grouped by Day Column
    day_columns = [[] for _ in range(7)]

    type_theme_map = {
        "my_calendar": {"theme": "theme-blue", "icon": "users"},
        "campaigns": {"theme": "theme-green", "icon": "flag"},
        "content": {"theme": "theme-rose", "icon": "file-text"},
        "team": {"theme": "theme-purple", "icon": "chart-no-axes-combined"},
        "external": {"theme": "theme-amber", "icon": "phone"},
    }

    # Add CalendarEvents
    for ce in cal_events:
        if ce.is_all_day:
            continue
        day_offset = (ce.date - start_of_week).days
        if 0 <= day_offset < 7:
            st_hour = ce.start_time.hour if ce.start_time else 9
            st_min = ce.start_time.minute if ce.start_time else 0
            et_hour = ce.end_time.hour if ce.end_time else (st_hour + 1)
            et_min = ce.end_time.minute if ce.end_time else 0

            time_str = f"{ce.start_time.strftime('%I:%M %p').lstrip('0')}" if ce.start_time else "All day"
            if ce.end_time:
                time_str += f" – {ce.end_time.strftime('%I:%M %p').lstrip('0')}"

            start_decimal = max(8.0, min(17.0, st_hour + st_min / 60.0))
            end_decimal = max(start_decimal + 0.5, min(18.0, et_hour + et_min / 60.0))
            top_px = int((start_decimal - 8.0) * 64)
            height_px = max(42, int((end_decimal - start_decimal) * 64) - 4)

            mapping = type_theme_map.get(ce.event_type, {"theme": "theme-blue", "icon": "users"})

            day_columns[day_offset].append({
                "title": ce.title,
                "time_label": time_str,
                "theme_class": mapping["theme"],
                "icon": mapping["icon"],
                "top_px": top_px,
                "height_px": height_px,
                "pk": str(ce.pk),
                "campaign_name": ce.campaign.name if ce.campaign else None,
            })

    # Add Tasks to Grid
    for t in tasks:
        day_offset = (t.due_on - start_of_week).days
        if 0 <= day_offset < 7:
            st_hour = 14
            top_px = int((st_hour - 8.0) * 64)
            day_columns[day_offset].append({
                "title": f"Task: {t.title}",
                "time_label": "Due 2:00 PM",
                "theme_class": "theme-amber",
                "icon": "list-checks",
                "top_px": top_px,
                "height_px": 54,
                "pk": str(t.pk),
                "campaign_name": t.campaign.name,
            })

    # Add ContentItems to Grid
    for item in items:
        day_offset = (item.planned_on - start_of_week).days
        if 0 <= day_offset < 7:
            st_hour = 11
            top_px = int((st_hour - 8.0) * 64)
            day_columns[day_offset].append({
                "title": f"Publish: {item.title}",
                "time_label": f"{item.channel} · 11:00 AM",
                "theme_class": "theme-rose",
                "icon": "file-text",
                "top_px": top_px,
                "height_px": 54,
                "pk": str(item.pk),
                "campaign_name": item.campaign.name,
            })

    # Mini Calendar Matrix
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdatescalendar(target_date.year, target_date.month)
    mini_weeks = []
    for week in month_days:
        w_days = []
        for d in week:
            w_days.append({
                "num": d.day,
                "date_str": d.strftime("%Y-%m-%d"),
                "is_current_month": (d.month == target_date.month),
                "is_today": (d == today),
                "is_selected": (d == target_date),
            })
        mini_weeks.append(w_days)

    if target_date.month == 1:
        prev_month_date = date(target_date.year - 1, 12, 1).strftime("%Y-%m-%d")
    else:
        prev_month_date = date(target_date.year, target_date.month - 1, 1).strftime("%Y-%m-%d")

    if target_date.month == 12:
        next_month_date = date(target_date.year + 1, 1, 1).strftime("%Y-%m-%d")
    else:
        next_month_date = date(target_date.year, target_date.month + 1, 1).strftime("%Y-%m-%d")

    mini_calendar = {
        "title": target_date.strftime("%B %Y"),
        "weeks": mini_weeks,
        "prev_month_date": prev_month_date,
        "next_month_date": next_month_date,
    }

    # Upcoming events for the sidebar
    upcoming_events = []
    future_events = list(CalendarEvent.objects.filter(
        organization=organization,
        date__gte=today,
    ).order_by("date", "start_time")[:8])

    for ev in future_events:
        if ev.date == today:
            group_label = "Today"
            dot_color = "dot-blue"
        elif ev.date == today + timedelta(days=1):
            group_label = "Tomorrow"
            dot_color = "dot-blue"
        else:
            group_label = ev.date.strftime("%A")
            dot_color = "dot-gray"

        t_label = ev.start_time.strftime("%I:%M %p").lstrip("0") if ev.start_time else "All day"
        upcoming_events.append({
            "group": group_label,
            "title": ev.title,
            "time": t_label,
            "dot": dot_color,
        })

    if not upcoming_events:
        for t in Task.objects.filter(campaign__organization=organization, due_on__gte=today).order_by("due_on")[:4]:
            grp = "Today" if t.due_on == today else ("Tomorrow" if t.due_on == today + timedelta(days=1) else t.due_on.strftime("%A"))
            upcoming_events.append({
                "group": grp,
                "title": t.title,
                "time": "Due date",
                "dot": "dot-blue" if t.due_on == today else "dot-gray",
            })

    org_campaigns = list(Campaign.objects.filter(organization=organization).order_by("name"))

    context = {
        "membership": membership,
        "week_days": week_days,
        "hours": hours,
        "all_day_events": all_day_events,
        "day_columns": day_columns,
        "mini_calendar": mini_calendar,
        "upcoming_events": upcoming_events,
        "date_range_label": date_range_label,
        "target_date": target_date.strftime("%Y-%m-%d"),
        "today_date": today_date_str,
        "prev_week_date": prev_week_date,
        "next_week_date": next_week_date,
        "view_mode": view_mode,
        "active_types": active_types,
        "org_campaigns": org_campaigns,
    }
    return render(request, "calendar.html", context)


@login_required
def calendar_event_create(request):
    membership = membership_for(request.user)
    if not membership:
        messages.error(request, "Organization workspace required.")
        return redirect("dashboard")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        event_type = request.POST.get("event_type", "my_calendar").strip()
        date_str = request.POST.get("date", "").strip()
        start_time_str = request.POST.get("start_time", "").strip()
        end_time_str = request.POST.get("end_time", "").strip()
        campaign_id = request.POST.get("campaign_id", "").strip()
        is_all_day = bool(request.POST.get("is_all_day"))

        if not title:
            messages.error(request, "Event title is required.")
            return redirect("calendar_view")

        try:
            ev_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else timezone.localdate()
        except ValueError:
            ev_date = timezone.localdate()

        st = None
        if start_time_str:
            try:
                st = datetime.strptime(start_time_str, "%H:%M").time()
            except ValueError:
                pass

        et = None
        if end_time_str:
            try:
                et = datetime.strptime(end_time_str, "%H:%M").time()
            except ValueError:
                pass

        campaign = None
        if campaign_id:
            try:
                campaign = Campaign.objects.get(pk=campaign_id, organization=membership.organization)
            except Campaign.DoesNotExist:
                pass

        CalendarEvent.objects.create(
            organization=membership.organization,
            campaign=campaign,
            title=title,
            event_type=event_type,
            date=ev_date,
            start_time=st,
            end_time=et,
            is_all_day=is_all_day,
            created_by=request.user,
        )
        messages.success(request, f"Event '{title}' scheduled.")
        return redirect(f"/calendar/?date={ev_date.strftime('%Y-%m-%d')}")

    return redirect("calendar_view")



