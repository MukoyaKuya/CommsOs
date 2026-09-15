from django.shortcuts import get_object_or_404
from .models import Membership, Campaign


def membership_for(user):
    return Membership.objects.select_related("organization").filter(user=user, active=True).first()


def campaign_for(user, pk):
    membership = membership_for(user)
    if membership is None:
        return get_object_or_404(Campaign.objects.none(), pk=pk)
    return get_object_or_404(Campaign, pk=pk, organization=membership.organization)


def can_manage(user, campaign):
    return Membership.objects.filter(
        user=user,
        organization=campaign.organization,
        active=True,
        role__in=["owner", "manager"],
    ).exists()
