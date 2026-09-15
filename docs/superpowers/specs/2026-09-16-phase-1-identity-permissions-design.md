# CommsOS Phase 1: Identity, Roles, and Permission Foundation

**Status:** Proposed for implementation review  
**Date:** 2026-09-16  
**Scope:** Domain services and permissions only; no full activity, collaboration, inventory, or public API implementation

## 1. Objective

Phase 1 establishes the identity and authorization foundation required by every later CommsOS workflow. Each account belongs to one organization, has exactly one fixed role in that organization, and cannot switch roles or workspaces. The current interface is the Communications Manager workspace. Other roles receive safe role-specific dashboard shells until their workflows are implemented.

The phase also adds invitation-based onboarding and staff profile metadata without moving the existing organization and membership tables or coupling business rules to HTML views or a future API framework.

## 2. Architectural decision

CommsOS remains a Django modular monolith. New identity behavior is introduced in an `accounts` app with explicit models, selectors, policies, and services.

The existing `core.Organization` and `core.Membership` models remain canonical during Phase 1 because campaigns, tasks, calendar records, selectors, services, migrations, and tests already depend on them. Moving these models between Django apps now would require a risky state/database migration with no immediate product benefit. The `accounts` app may depend on these two legacy ownership models, but new identity rules must live in `accounts` rather than expanding `core`.

Future apps will call the same policy and service functions:

- `work`: activities, assignments, tasks, checklists, and deliverables.
- `collaboration`: contextual threads, progress updates, requests, and notifications.
- `assets`: inventory, event issue/return, quantities, and condition history.
- Django Ninja routers: transport adapters over the same services; they will not contain business authorization rules.

## 3. Role model

`Membership.Role` will use these user-facing roles:

| Role | Phase 1 authority |
| --- | --- |
| Communications Manager | Full organization administration; invite/deactivate staff; edit profiles; access the existing manager dashboard and campaign-management functions |
| Communications Officer | View own role dashboard shell and own profile; future assignment/deliverable permissions are deferred |
| Support Staff | View own role dashboard shell and own profile; future external-activity tasks are deferred |
| Intern | View own role dashboard shell and own profile; future event checklists/material accountability is deferred |
| Viewer | Read-only dashboard shell; future scoped reporting access is deferred |

There may be multiple accounts in any role, including multiple Communications Managers. Services must prevent deactivation of the last active Communications Manager in an organization.

Existing role data is migrated as follows:

- `owner` and `manager` → `communications_manager`
- `contributor` → `communications_officer`
- `viewer` → `viewer`

Role selection on the login screen is an assertion, not a permission grant. Authentication succeeds only when the submitted role matches the active membership stored for that account. A user cannot edit their own role or organization.

## 4. Data model

### Existing models retained

`core.Organization`

- Remains the organization tenant boundary.

`core.Membership`

- Remains unique on `(organization, user)`.
- Continues to carry `role` and `active`.
- Role choices are replaced with the five Phase 1 roles.
- A normal user may have only one membership across the system. This invariant is enforced by a database uniqueness constraint on `user` in addition to service validation.

### New `accounts.StaffProfile`

One-to-one with `Membership`:

- `department`
- `job_title`
- `job_group`
- `rank`
- `skills` as a JSON list of normalized strings
- `job_description`
- `phone`
- `supervisor`, an optional membership reference
- created/updated timestamps

Supervisor assignment must stay within the same organization and cannot point to the profile's own membership. Profile metadata informs future assignment decisions but never grants permissions.

### New `accounts.Invitation`

- organization
- normalized email
- assigned role
- invited profile metadata needed at onboarding
- cryptographically random token hash; the raw token is never stored
- `expires_at`
- `accepted_at`
- `revoked_at`
- `invited_by`
- created/updated timestamps

Only one pending, unexpired invitation may exist for a given organization and email. Invitations are single-use and organization-bound. Phase 1 displays a copyable acceptance link to the manager; email delivery is explicitly deferred.

## 5. Service boundary

All mutations occur through transaction-aware services. Views and future Ninja endpoints may bind input and translate errors, but must not duplicate these rules.

Required services:

- `create_invitation(actor, organization, email, role, profile_data)`
- `revoke_invitation(actor, invitation)`
- `accept_invitation(raw_token, account_data, password)`
- `update_staff_profile(actor, membership, profile_data)`
- `change_member_role(actor, membership, role)`
- `deactivate_member(actor, membership)`
- `reactivate_member(actor, membership)`

Rules:

- The actor must be an active Communications Manager in the same organization for management operations.
- Posted organization identifiers are never trusted to establish scope.
- Invitation acceptance validates token hash, expiry, revocation, prior use, email uniqueness, and membership uniqueness inside one transaction.
- Role changes and deactivation lock the affected organization memberships when checking the last-manager invariant.
- Historical memberships are deactivated rather than deleted.
- Domain failures use typed exceptions such as `PermissionDenied`, `InvitationExpired`, `InvitationAlreadyUsed`, `LastManagerRequired`, and `CrossOrganizationAccess`.

## 6. Policy and selector boundary

`accounts.policies` provides reusable, side-effect-free checks such as:

- `is_communications_manager(membership)`
- `can_manage_members(actor_membership)`
- `can_view_member(actor_membership, target_membership)`
- `can_edit_profile(actor_membership, target_membership)`
- `can_access_manager_workspace(membership)`

`accounts.selectors` provides organization-scoped reads:

- active membership for a user
- member directory for an organization
- member by ID within the actor's organization
- pending invitations within the actor's organization

No view or future API operation fetches a membership, profile, or invitation by bare primary key.

## 7. Authentication and dashboard routing

The unconditional development auto-login middleware conflicts with role validation and must be removed from the default middleware stack. If demo auto-login remains useful, it must be behind an explicit environment setting that is off by default and must never run when `DEBUG` is false.

The shared login form asks for username/email, password, and role. The login service/form validates credentials and confirms that the chosen role matches the one active membership. A mismatch returns a generic authentication error and does not reveal another user's assigned role.

After login, a dashboard router resolves the active membership once and renders:

- Communications Manager → existing manager dashboard
- Communications Officer → officer dashboard shell
- Support Staff → support dashboard shell
- Intern → intern dashboard shell
- Viewer → viewer dashboard shell

Direct access to manager-only campaign mutations is blocked at the service boundary and protected in views. Navigation is rendered from the membership role, but hidden links are never treated as authorization.

## 8. Manager-facing Phase 1 interface

Phase 1 makes the existing Team Directory and Invite Teammates navigation functional for Communications Managers:

- directory grouped/filterable by role and active state
- profile detail/edit form
- create invitation form and copyable acceptance link
- pending invitation list with expiry and revoke action
- deactivate/reactivate member actions
- visible role, department, title, rank/job group, skills, and supervisor

Non-managers cannot access these routes. Other dashboards are intentionally minimal and identify the signed-in role; their operational workflows belong to later phases.

## 9. Security and privacy

- Use Django sessions, CSRF protection, password validators, and standard password hashing.
- Generate invitation tokens with a cryptographically secure generator and store only a one-way hash.
- Use a short configurable expiry, defaulting to 72 hours.
- Prevent open redirects after login/invitation acceptance.
- Avoid exposing whether an email is already registered in public error messages.
- Keep staff profile and invitation queries organization-scoped.
- Record management actions without storing raw invitation tokens or passwords.

Phase 1 introduces a general organization audit record only if the current campaign-bound `AuditEvent` cannot represent membership actions cleanly. Membership audit events must not be forced to reference a campaign.

## 10. Testing strategy

Implementation follows test-driven development. Required tests include:

- each legacy role migrates to the intended new role
- one user cannot have memberships in two organizations
- selected login role must match stored membership role
- dashboard routing for all five roles
- only active Communications Managers can invite or manage members
- cross-organization profile/invitation access is denied
- invitation tokens are hashed, expire, are single-use, and can be revoked
- invitation acceptance creates one user, membership, and profile atomically
- duplicate acceptance and concurrent-style retries do not duplicate accounts
- supervisor must belong to the same organization and cannot be self
- the last active Communications Manager cannot be demoted or deactivated
- deactivated users cannot enter protected workspaces
- existing campaign authorization and organization-isolation tests remain green after role migration

Quality gates:

```text
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
npm run build:css
```

A browser smoke test covers manager login, invitation creation, invitation acceptance, role dashboard routing, directory display, and deactivation.

## 11. Migration and compatibility strategy

1. Add the `accounts` app and its models without modifying current data.
2. Add new role values and a data migration from legacy roles.
3. Add the one-membership-per-user constraint only after a migration verifies there are no duplicates; fail clearly rather than silently deleting data.
4. Create profiles for existing memberships with blank optional metadata.
5. Update campaign permission checks from legacy owner/manager strings to shared account policies.
6. Replace direct membership-role comparisons in templates with view-provided capabilities where practical.
7. Remove default auto-login and introduce explicit demo-only configuration if retained.

Existing uncommitted changes in `core/tests.py` and `templates/campaigns_list.html` are unrelated and must be preserved.

## 12. Explicitly deferred

- Activities, task/checklist assignment, and status workflows
- Officer deliverable uploads and manager review
- Support Staff external-activity workflows
- Intern inventory check-out/return workflows
- Collaboration threads, forum, mentions, and notifications
- Django Ninja endpoints
- Email delivery of invitations
- Real-time messaging and WebSockets
- Full UX redesign and objective/performance analytics

## 13. Acceptance criteria

Phase 1 is complete when:

1. A Communications Manager can invite multiple users into any supported role and manage their profiles.
2. An invitation can be accepted once to create a password-protected account in the inviting organization.
3. Every account has one organization and one role and cannot switch either.
4. Each supported role lands on its own dashboard route/template.
5. Non-managers cannot use membership-management services or pages.
6. The last active Communications Manager cannot be removed or demoted.
7. Existing manager campaign workflows continue to work with the new role value.
8. Tenant-isolation, authentication, migration, and full regression tests pass.
