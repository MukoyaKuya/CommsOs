from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from accounts.forms import RoleLoginForm
from accounts.selectors import active_membership_for
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

