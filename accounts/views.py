from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.exceptions import IdentityDomainError
from accounts.forms import InvitationAcceptanceForm, InvitationForm, RoleLoginForm, StaffProfileForm
from accounts.policies import can_manage_members
from accounts.selectors import active_membership_for, member_for, members_for, pending_invitations_for
from accounts.services import accept_invitation, create_invitation, deactivate_member, reactivate_member, revoke_invitation, update_staff_profile
from core import views as core_views
from core.models import Membership


class RoleLoginView(LoginView):
    template_name = "login.html"
    authentication_form = RoleLoginForm
    redirect_authenticated_user = True


@login_required
def dashboard_router(request):
    membership = active_membership_for(request.user)
    if membership is None:
        raise PermissionDenied("An active organization membership is required.")
    if membership.role == Membership.Role.COMMUNICATIONS_MANAGER:
        return core_views.dashboard(request)
    template_name = {
        Membership.Role.COMMUNICATIONS_OFFICER: "accounts/dashboard_officer.html",
        Membership.Role.SUPPORT_STAFF: "accounts/dashboard_support.html",
        Membership.Role.INTERN: "accounts/dashboard_intern.html",
        Membership.Role.VIEWER: "accounts/dashboard_viewer.html",
    }.get(membership.role)
    if template_name is None:
        raise PermissionDenied("The assigned role is not supported.")
    return render(request, template_name, {"membership": membership})


def _manager_for(request):
    membership = active_membership_for(request.user)
    if not can_manage_members(membership):
        raise PermissionDenied("Communications Manager access is required.")
    return membership


@login_required
def team_directory(request):
    actor = _manager_for(request)
    return render(
        request,
        "accounts/team_directory.html",
        {
            "membership": actor,
            "members": members_for(actor),
            "invitations": pending_invitations_for(actor),
        },
    )


@login_required
def invitation_create(request):
    actor = _manager_for(request)
    form = InvitationForm(request.POST or None)
    raw_token = None
    if request.method == "POST" and form.is_valid():
        try:
            _invitation, raw_token = create_invitation(
                actor,
                form.cleaned_data["email"],
                form.cleaned_data["role"],
                form.profile_data(),
            )
        except IdentityDomainError as exc:
            form.add_error(None, str(exc))
    invitation_url = None
    if raw_token:
        invitation_url = request.build_absolute_uri(reverse("invitation_accept", args=[raw_token]))
    return render(
        request,
        "accounts/invitation_form.html",
        {"membership": actor, "form": form, "invitation_url": invitation_url},
    )


def invitation_accept(request, token):
    form = InvitationAcceptanceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            accept_invitation(
                token,
                form.cleaned_data["username"],
                form.cleaned_data["password1"],
                form.cleaned_data["first_name"],
                form.cleaned_data["last_name"],
            )
        except (IdentityDomainError, ValueError) as exc:
            form.add_error(None, str(exc))
        else:
            return redirect("login")
    return render(request, "accounts/invitation_accept.html", {"form": form})


@login_required
def staff_profile_edit(request, pk):
    actor = _manager_for(request)
    target = member_for(actor, pk)
    profile = target.staff_profile
    form = StaffProfileForm(request.POST or None, instance=profile)
    form.fields["supervisor"].queryset = members_for(actor).filter(active=True).exclude(pk=target.pk)
    if request.method == "POST" and form.is_valid():
        update_staff_profile(actor, target.pk, form.cleaned_data)
        return redirect("team_directory")
    return render(request, "accounts/profile_form.html", {"membership": actor, "target": target, "form": form})


@login_required
def member_deactivate(request, pk):
    actor = _manager_for(request)
    if request.method != "POST":
        raise PermissionDenied("POST required.")
    deactivate_member(actor, pk)
    return redirect("team_directory")


@login_required
def member_reactivate(request, pk):
    actor = _manager_for(request)
    if request.method != "POST":
        raise PermissionDenied("POST required.")
    reactivate_member(actor, pk)
    return redirect("team_directory")


@login_required
def invitation_revoke(request, pk):
    actor = _manager_for(request)
    if request.method != "POST":
        raise PermissionDenied("POST required.")
    revoke_invitation(actor, pk)
    return redirect("team_directory")
