from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.landing, name="landing"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("campaigns/", views.campaigns_list, name="campaigns_list"),
    path("campaigns/seed-samples/", views.campaigns_seed_samples, name="campaigns_seed_samples"),
    path("campaigns/clear-samples/", views.campaigns_clear_samples, name="campaigns_clear_samples"),
    path("campaigns/new/", views.campaign_create, name="campaign_create"),
    path("campaigns/<uuid:pk>/", views.campaign_detail, name="campaign_detail"),
    path("campaigns/<uuid:pk>/edit/", views.campaign_edit, name="campaign_edit"),
    path("campaigns/<uuid:pk>/strategy/edit/", views.strategy_edit, name="strategy_edit"),
    path(
        "campaigns/<uuid:pk>/strategy/generate/",
        views.strategy_generate,
        name="strategy_generate",
    ),
    path(
        "campaigns/<uuid:pk>/strategy/approve/",
        views.strategy_approve,
        name="strategy_approve",
    ),
    path("campaigns/<uuid:pk>/plan/generate/", views.plan_generate, name="plan_generate"),
    path("campaigns/<uuid:pk>/plan/apply/", views.plan_apply, name="plan_apply"),
    path(
        "campaigns/<uuid:pk>/content/<uuid:item_pk>/generate/",
        views.content_generate,
        name="content_generate",
    ),
    path(
        "campaigns/<uuid:pk>/content/<uuid:item_pk>/edit/",
        views.content_edit,
        name="content_edit",
    ),
    path(
        "campaigns/<uuid:pk>/observations/add/",
        views.observation_add,
        name="observation_add",
    ),
    path(
        "campaigns/<uuid:pk>/insight/generate/",
        views.insight_generate,
        name="insight_generate",
    ),
    path(
        "campaigns/<uuid:pk>/recommendation/apply/",
        views.recommendation_apply,
        name="recommendation_apply",
    ),
    path("campaigns/<uuid:pk>/report/", views.report, name="report"),
    path("campaigns/<uuid:pk>/summary/", views.campaign_summary, name="campaign_summary"),
]
