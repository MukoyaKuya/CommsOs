from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone

from accounts.exceptions import (
    CrossOrganizationAccess,
    InvitationAlreadyUsed,
    InvitationConflict,
    InvitationExpired,
    InvitationInvalid,
    InvitationRevoked,
    LastManagerRequired,
    PermissionDenied,
)
from accounts.models import Invitation, StaffProfile
from accounts.policies import can_manage_members
from core.models import Membership


def _require_manager(actor):
    if not can_manage_members(actor):
        raise PermissionDenied("An active Communications Manager is required.")


def _member_in_actor_organization(actor, membership_id):
    _require_manager(actor)
    try:
        membership = Membership.objects.select_related("organization", "user").get(
            pk=membership_id
        )
    except Membership.DoesNotExist as exc:
        raise CrossOrganizationAccess("Member is not available.") from exc
    if membership.organization_id != actor.organization_id:
        raise CrossOrganizationAccess("Member is not available.")
    return membership


def create_invitation(actor, email, role, profile_data):
    _require_manager(actor)
    valid_roles = {value for value, _label in Membership.Role.choices}
    if role not in valid_roles:
        raise InvitationConflict("Unsupported role.")
    normalized_email = email.strip()
    if get_user_model().objects.filter(email__iexact=normalized_email).exists():
        raise InvitationConflict("An account already uses this email.")
    now = timezone.now()
    if Invitation.objects.filter(
        organization=actor.organization,
        email__iexact=normalized_email,
        accepted_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=now,
    ).exists():
        raise InvitationConflict("A pending invitation already exists.")
    return Invitation.issue(
        organization=actor.organization,
        email=normalized_email,
        role=role,
        invited_by=actor,
        profile_data=profile_data,
    )


@transaction.atomic
def revoke_invitation(actor, invitation_id):
    _require_manager(actor)
    invitation = Invitation.objects.select_for_update().get(pk=invitation_id)
    if invitation.organization_id != actor.organization_id:
        raise CrossOrganizationAccess("Invitation is not available.")
    if invitation.accepted_at:
        raise InvitationAlreadyUsed("Invitation has already been accepted.")
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at", "updated_at"])
    return invitation


@transaction.atomic
def accept_invitation(raw_token, username, password, first_name="", last_name=""):
    token_hash = Invitation.hash_token(raw_token)
    try:
        invitation = Invitation.objects.select_for_update().get(token_hash=token_hash)
    except Invitation.DoesNotExist as exc:
        raise InvitationInvalid("Invitation is invalid.") from exc
    if invitation.accepted_at:
        raise InvitationAlreadyUsed("Invitation has already been accepted.")
    if invitation.revoked_at:
        raise InvitationRevoked("Invitation has been revoked.")
    if invitation.expires_at <= timezone.now():
        raise InvitationExpired("Invitation has expired.")

    user_model = get_user_model()
    if user_model.objects.filter(username__iexact=username).exists():
        raise InvitationConflict("Username is unavailable.")
    if user_model.objects.filter(email__iexact=invitation.email).exists():
        raise InvitationConflict("An account already exists for this email.")
    prospective_user = user_model(
        username=username.strip(),
        email=invitation.email,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
    )
    validate_password(password, prospective_user)
    prospective_user.set_password(password)
    prospective_user.save()
    membership = Membership.objects.create(
        user=prospective_user,
        organization=invitation.organization,
        role=invitation.role,
        active=True,
    )
    profile = StaffProfile(membership=membership, **invitation.profile_data)
    profile.full_clean()
    profile.save()
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at", "updated_at"])
    return membership


@transaction.atomic
def update_staff_profile(actor, membership_id, profile_data):
    membership = _member_in_actor_organization(actor, membership_id)
    profile, _created = StaffProfile.objects.get_or_create(membership=membership)
    allowed = {
        "department",
        "job_title",
        "job_group",
        "rank",
        "skills",
        "job_description",
        "phone",
        "supervisor",
    }
    for field, value in profile_data.items():
        if field in allowed:
            setattr(profile, field, value)
    profile.full_clean()
    profile.save()
    return profile


def _ensure_another_manager(target):
    if target.active and target.role == Membership.Role.COMMUNICATIONS_MANAGER:
        others = Membership.objects.filter(
            organization=target.organization,
            role=Membership.Role.COMMUNICATIONS_MANAGER,
            active=True,
        ).exclude(pk=target.pk)
        if not others.exists():
            raise LastManagerRequired("At least one active Communications Manager is required.")


@transaction.atomic
def change_member_role(actor, membership_id, role):
    membership = _member_in_actor_organization(actor, membership_id)
    membership = Membership.objects.select_for_update().get(pk=membership.pk)
    if role != Membership.Role.COMMUNICATIONS_MANAGER:
        _ensure_another_manager(membership)
    membership.role = role
    membership.full_clean()
    membership.save(update_fields=["role", "updated_at"])
    return membership


@transaction.atomic
def deactivate_member(actor, membership_id):
    membership = _member_in_actor_organization(actor, membership_id)
    membership = Membership.objects.select_for_update().get(pk=membership.pk)
    _ensure_another_manager(membership)
    membership.active = False
    membership.save(update_fields=["active", "updated_at"])
    return membership


@transaction.atomic
def reactivate_member(actor, membership_id):
    membership = _member_in_actor_organization(actor, membership_id)
    membership.active = True
    membership.save(update_fields=["active", "updated_at"])
    return membership

