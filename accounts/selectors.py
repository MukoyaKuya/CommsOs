from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import Invitation
from core.models import Membership


def active_membership_for(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return (
        Membership.objects.select_related("organization", "user", "staff_profile")
        .filter(user=user, active=True)
        .first()
    )


def members_for(actor_membership):
    if actor_membership is None or not actor_membership.active:
        return Membership.objects.none()
    return (
        Membership.objects.filter(organization=actor_membership.organization)
        .select_related("organization", "user", "staff_profile")
        .order_by("user__first_name", "user__last_name", "user__username")
    )


def member_for(actor_membership, pk):
    organization_id = getattr(actor_membership, "organization_id", None)
    return get_object_or_404(
        Membership.objects.select_related("organization", "user", "staff_profile"),
        pk=pk,
        organization_id=organization_id,
    )


def pending_invitations_for(actor_membership):
    if actor_membership is None or not actor_membership.active:
        return Invitation.objects.none()
    return Invitation.objects.filter(
        organization=actor_membership.organization,
        accepted_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at")

