class IdentityDomainError(Exception):
    pass


class PermissionDenied(IdentityDomainError):
    pass


class CrossOrganizationAccess(PermissionDenied):
    pass


class InvitationInvalid(IdentityDomainError):
    pass


class InvitationExpired(InvitationInvalid):
    pass


class InvitationAlreadyUsed(InvitationInvalid):
    pass


class InvitationRevoked(InvitationInvalid):
    pass


class InvitationConflict(IdentityDomainError):
    pass


class LastManagerRequired(IdentityDomainError):
    pass

