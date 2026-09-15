from core.models import Membership


def is_communications_manager(membership):
    return bool(
        membership
        and membership.active
        and membership.role == Membership.Role.COMMUNICATIONS_MANAGER
    )


def can_manage_members(membership):
    return is_communications_manager(membership)


def can_view_member(actor_membership, target_membership):
    return bool(
        actor_membership
        and actor_membership.active
        and target_membership
        and actor_membership.organization_id == target_membership.organization_id
    )


def can_edit_profile(actor_membership, target_membership):
    return can_manage_members(actor_membership) and can_view_member(
        actor_membership, target_membership
    )


def can_access_manager_workspace(membership):
    return is_communications_manager(membership)

