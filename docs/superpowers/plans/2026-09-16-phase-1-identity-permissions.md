# Phase 1 Identity and Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build fixed single-organization roles, staff profiles, secure invitation onboarding, reusable authorization services, and role-aware dashboards while preserving existing campaign behavior.

**Architecture:** Keep `core.Organization` and `core.Membership` canonical to avoid a destructive cross-app migration. Add an `accounts` domain app containing identity models, policies, selectors, services, forms, and web adapters; existing views and future Django Ninja routers call these services rather than owning permission rules.

**Tech Stack:** Django 6, Django ORM/migrations, Django sessions/forms/templates, Python `secrets` and SHA-256, Django `TestCase`, Tailwind build pipeline.

**Spec:** `docs/superpowers/specs/2026-09-16-phase-1-identity-permissions-design.md`

## Global Constraints

- Each account has exactly one active or historical membership and therefore one organization and one fixed role.
- Supported roles are `communications_manager`, `communications_officer`, `support_staff`, `intern`, and `viewer`.
- Multiple Communications Managers are allowed, but the last active manager cannot be demoted or deactivated.
- Organization scope comes from the authenticated membership, never posted `organization_id` data.
- Invitation tokens are single-use, expire after 72 hours by default, and are stored only as hashes.
- Existing uncommitted changes in `core/tests.py` and `templates/campaigns_list.html` must be preserved.
- Domain services own authorization, transactions, and state changes; templates and API adapters do not.
- Implementation uses test-driven development: observe each focused test fail before adding production code.

---

## File Structure

- `accounts/models.py`: staff profiles and invitation persistence only.
- `accounts/policies.py`: pure role/capability predicates.
- `accounts/selectors.py`: organization-scoped membership/profile/invitation queries.
- `accounts/services.py`: invitation and membership-management use cases.
- `accounts/exceptions.py`: typed domain failures.
- `accounts/forms.py`: login, invitation, acceptance, and profile validation.
- `accounts/views.py`: thin HTML adapters and dashboard routing.
- `accounts/urls.py`: identity and team-management routes.
- `accounts/tests/`: tests split by models, policies, services, authentication, and views.
- `accounts/templates/accounts/`: role dashboards, directory, invitation, and profile screens.
- `core/models.py`: role enum and one-membership-per-user constraint.
- `core/services.py`, `core/views.py`, `core/selectors.py`: migrate existing manager authorization to shared policies.
- `config/settings.py`, `config/urls.py`: app registration, login routing, and safe demo auto-login configuration.

---

### Task 1: Create the Accounts Domain and Migrate Roles Safely

**Files:**
- Create: `accounts/__init__.py`
- Create: `accounts/apps.py`
- Create: `accounts/models.py`
- Create: `accounts/migrations/0001_initial.py` via `makemigrations`
- Create: `accounts/tests/__init__.py`
- Create: `accounts/tests/test_models.py`
- Modify: `core/models.py`
- Create: `core/migrations/0003_phase1_roles.py` via `makemigrations`, then edit its data operation
- Modify: `config/settings.py`

**Interfaces:**
- Produces: `StaffProfile`, `Invitation`, and `Membership.Role` values consumed by all later tasks.
- Produces: database invariant `UniqueConstraint(fields=["user"], name="one_membership_per_user")`.

- [ ] **Step 1: Write failing model tests**

```python
class IdentityModelTests(TestCase):
    def test_user_can_have_only_one_membership(self):
        Membership.objects.create(user=self.user, organization=self.org, role=Membership.Role.COMMUNICATIONS_MANAGER)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(user=self.user, organization=self.other_org, role=Membership.Role.VIEWER)

    def test_profile_rejects_self_supervisor(self):
        membership = Membership.objects.create(user=self.user, organization=self.org, role=Membership.Role.INTERN)
        profile = StaffProfile(membership=membership, supervisor=membership)
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_invitation_never_stores_raw_token(self):
        invitation, raw_token = Invitation.issue(self.org, "officer@example.com", Membership.Role.COMMUNICATIONS_OFFICER, self.manager)
        self.assertNotEqual(invitation.token_hash, raw_token)
        self.assertTrue(invitation.matches(raw_token))
```

- [ ] **Step 2: Run tests and confirm missing models/roles fail**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_models -v 2`  
Expected: FAIL because the `accounts` app and new role constants do not exist.

- [ ] **Step 3: Implement the minimal models and constraints**

Define `StaffProfile.clean()` to reject self/cross-organization supervisors. Define `Invitation.issue(...) -> tuple[Invitation, str]` with `secrets.token_urlsafe(32)`, `hashlib.sha256`, normalized email, and `timezone.now() + timedelta(hours=72)`. Define `matches(raw_token: str) -> bool` using `secrets.compare_digest`.

- [ ] **Step 4: Generate and edit migrations**

Run: `.\.venv\Scripts\python.exe manage.py makemigrations core accounts`

Add a `RunPython` operation before constraining role choices:

```python
def migrate_roles(apps, schema_editor):
    Membership = apps.get_model("core", "Membership")
    Membership.objects.filter(role__in=["owner", "manager"]).update(role="communications_manager")
    Membership.objects.filter(role="contributor").update(role="communications_officer")
```

Before adding the unique user constraint, raise `RuntimeError` when duplicate `user_id` values exist; do not discard data.

- [ ] **Step 5: Run focused tests and migration checks**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_models -v 2`  
Expected: PASS.  
Run: `.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`  
Expected: `No changes detected`.

- [ ] **Step 6: Commit**

```powershell
git add accounts core/models.py core/migrations config/settings.py
git commit -m "feat(accounts): add fixed roles and identity models"
```

### Task 2: Add Reusable Policies and Organization-Scoped Selectors

**Files:**
- Create: `accounts/policies.py`
- Create: `accounts/selectors.py`
- Create: `accounts/tests/test_policies.py`
- Create: `accounts/tests/test_selectors.py`

**Interfaces:**
- Consumes: `Membership.Role` and `StaffProfile` from Task 1.
- Produces: `is_communications_manager`, `can_manage_members`, `can_view_member`, `can_edit_profile`, `can_access_manager_workspace`.
- Produces: `active_membership_for(user)`, `members_for(actor_membership)`, `member_for(actor_membership, pk)`, `pending_invitations_for(actor_membership)`.

- [ ] **Step 1: Write failing policy and isolation tests**

```python
def test_only_active_manager_can_manage_members(self):
    self.assertTrue(can_manage_members(self.manager))
    self.assertFalse(can_manage_members(self.officer))
    self.manager.active = False
    self.assertFalse(can_manage_members(self.manager))

def test_member_selector_hides_other_organization(self):
    with self.assertRaises(Http404):
        member_for(self.manager, self.other_membership.pk)
```

- [ ] **Step 2: Run focused tests and confirm imports fail**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_policies accounts.tests.test_selectors -v 2`  
Expected: FAIL because policy and selector functions do not exist.

- [ ] **Step 3: Implement pure policies and scoped selectors**

Selectors must always filter `organization=actor_membership.organization`; `active_membership_for` uses `select_related("organization", "staff_profile")` and returns one active membership or `None`.

- [ ] **Step 4: Run focused tests**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_policies accounts.tests.test_selectors -v 2`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add accounts/policies.py accounts/selectors.py accounts/tests
git commit -m "feat(accounts): add tenant-scoped identity policies"
```

### Task 3: Implement Secure Invitation Services

**Files:**
- Create: `accounts/exceptions.py`
- Create: `accounts/services.py`
- Create: `accounts/tests/test_invitation_services.py`

**Interfaces:**
- Consumes: models and policies from Tasks 1–2.
- Produces: `create_invitation(actor, email, role, profile_data) -> tuple[Invitation, str]`.
- Produces: `revoke_invitation(actor, invitation_id) -> Invitation`.
- Produces: `accept_invitation(raw_token, username, password, first_name="", last_name="") -> Membership`.

- [ ] **Step 1: Write failing authorization and lifecycle tests**

```python
def test_manager_can_invite_officer_and_token_is_single_use(self):
    invitation, token = create_invitation(self.manager, "new@example.com", Membership.Role.COMMUNICATIONS_OFFICER, {"job_title": "Officer"})
    membership = accept_invitation(token, "new_officer", "A-strong-test-password-2026")
    self.assertEqual(membership.organization, self.manager.organization)
    self.assertEqual(membership.staff_profile.job_title, "Officer")
    with self.assertRaises(InvitationAlreadyUsed):
        accept_invitation(token, "second", "A-strong-test-password-2026")

def test_officer_cannot_invite(self):
    with self.assertRaises(PermissionDenied):
        create_invitation(self.officer, "blocked@example.com", Membership.Role.INTERN, {})
```

Also add tests for expired, revoked, invalid, duplicate-email, and cross-organization invitation access.

- [ ] **Step 2: Run tests and confirm missing services fail**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_invitation_services -v 2`  
Expected: FAIL because services and typed exceptions do not exist.

- [ ] **Step 3: Implement typed exceptions and transactional services**

Use `transaction.atomic()`, `select_for_update()` on invitation acceptance, Django `validate_password`, `get_user_model().objects.create_user`, and create Membership/Profile before setting `accepted_at`. Never accept `organization_id` from the caller.

- [ ] **Step 4: Run focused tests**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_invitation_services -v 2`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add accounts/exceptions.py accounts/services.py accounts/tests/test_invitation_services.py
git commit -m "feat(accounts): add secure invitation onboarding"
```

### Task 4: Implement Member Profile and Lifecycle Services

**Files:**
- Modify: `accounts/services.py`
- Create: `accounts/tests/test_member_services.py`

**Interfaces:**
- Produces: `update_staff_profile(actor, membership_id, profile_data) -> StaffProfile`.
- Produces: `change_member_role(actor, membership_id, role) -> Membership`.
- Produces: `deactivate_member(actor, membership_id) -> Membership`.
- Produces: `reactivate_member(actor, membership_id) -> Membership`.

- [ ] **Step 1: Write failing service tests**

```python
def test_last_manager_cannot_be_deactivated(self):
    with self.assertRaises(LastManagerRequired):
        deactivate_member(self.manager, self.manager.pk)

def test_manager_cannot_modify_other_organization_profile(self):
    with self.assertRaises(CrossOrganizationAccess):
        update_staff_profile(self.manager, self.other_member.pk, {"rank": "Senior"})
```

Add success tests for multiple managers, reactivation, valid same-organization supervisor, and role changes.

- [ ] **Step 2: Run tests and confirm missing functions fail**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_member_services -v 2`  
Expected: FAIL because lifecycle services do not exist.

- [ ] **Step 3: Implement services with locking**

Lock organization manager memberships before demotion/deactivation, count active managers excluding the target, and raise `LastManagerRequired` when the result would be zero. Run `StaffProfile.full_clean()` before saving profile changes.

- [ ] **Step 4: Run focused tests**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_member_services -v 2`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add accounts/services.py accounts/tests/test_member_services.py
git commit -m "feat(accounts): enforce staff lifecycle permissions"
```

### Task 5: Replace Unsafe Auto-Login and Add Role-Validated Authentication

**Files:**
- Modify: `config/settings.py`
- Modify: `config/urls.py`
- Modify: `core/middleware.py`
- Create: `accounts/forms.py`
- Create: `accounts/views.py`
- Create: `accounts/urls.py`
- Create: `accounts/tests/test_authentication.py`
- Modify: `templates/login.html`

**Interfaces:**
- Produces: `RoleLoginForm`, `login_view`, and `dashboard_router`.
- Consumes: `active_membership_for` and role constants.

- [ ] **Step 1: Write failing login and routing tests**

```python
def test_login_rejects_role_mismatch_without_revealing_actual_role(self):
    response = self.client.post(reverse("login"), {"username": self.user.username, "password": self.password, "role": Membership.Role.INTERN})
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, "Unable to sign in with those details")
    self.assertFalse(response.wsgi_request.user.is_authenticated)

def test_manager_dashboard_routes_to_existing_manager_view(self):
    self.client.force_login(self.manager.user)
    response = self.client.get(reverse("dashboard"))
    self.assertTemplateUsed(response, "dashboard.html")
```

Add one routing test for each role and a deactivated-member denial test.

- [ ] **Step 2: Run tests and confirm current auto-login/wrong routing failures**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_authentication -v 2`  
Expected: FAIL because auto-login authenticates anonymous requests and role routing does not exist.

- [ ] **Step 3: Implement role login and safe demo flag**

Remove `AutoLoginMiddleware` from default `MIDDLEWARE`. Add it only when `DEBUG` and `COMMSOS_DEMO_AUTO_LOGIN=1`. `RoleLoginForm.confirm_login_allowed` must validate active membership and constant-time compare the posted role to stored role. Route each role to a dedicated template; call the existing manager dashboard logic for managers.

- [ ] **Step 4: Run focused and existing login tests**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_authentication core.tests -v 2`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add accounts config/settings.py config/urls.py core/middleware.py templates/login.html
git commit -m "feat(auth): validate fixed roles at sign in"
```

### Task 6: Build Manager Team Directory and Invitation Pages

**Files:**
- Modify: `accounts/forms.py`
- Modify: `accounts/views.py`
- Modify: `accounts/urls.py`
- Create: `accounts/templates/accounts/team_directory.html`
- Create: `accounts/templates/accounts/invitation_form.html`
- Create: `accounts/templates/accounts/invitation_accept.html`
- Create: `accounts/templates/accounts/profile_form.html`
- Create: `accounts/templates/accounts/dashboard_officer.html`
- Create: `accounts/templates/accounts/dashboard_support.html`
- Create: `accounts/templates/accounts/dashboard_intern.html`
- Create: `accounts/templates/accounts/dashboard_viewer.html`
- Create: `accounts/tests/test_views.py`
- Modify: `templates/base.html`

**Interfaces:**
- Consumes: selectors/services from Tasks 2–4.
- Produces named routes: `team_directory`, `invitation_create`, `invitation_revoke`, `invitation_accept`, `staff_profile_edit`, `member_deactivate`, `member_reactivate`.

- [ ] **Step 1: Write failing page authorization and workflow tests**

```python
def test_manager_can_create_invitation_from_team_page(self):
    self.client.force_login(self.manager.user)
    response = self.client.post(reverse("invitation_create"), {"email": "staff@example.com", "role": Membership.Role.SUPPORT_STAFF, "job_title": "Driver"})
    self.assertRedirects(response, reverse("team_directory"))
    self.assertTrue(Invitation.objects.filter(email="staff@example.com").exists())

def test_officer_cannot_open_team_directory(self):
    self.client.force_login(self.officer.user)
    self.assertEqual(self.client.get(reverse("team_directory")).status_code, 403)
```

Add acceptance, revoke, edit, deactivate/reactivate, CSRF-backed POST, and role-navigation tests.

- [ ] **Step 2: Run tests and confirm routes fail**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_views -v 2`  
Expected: FAIL with missing routes/templates.

- [ ] **Step 3: Implement thin forms/views/templates**

Forms expose role/profile fields but never organization. Views obtain `actor = active_membership_for(request.user)`, call services, translate typed exceptions to form/non-field messages, and use POST for revoke/deactivate/reactivate. The raw invitation token appears only immediately after creation as a copyable link.

- [ ] **Step 4: Run focused tests and build CSS**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_views -v 2`  
Expected: PASS.  
Run: `npm run build:css`  
Expected: exit 0.

- [ ] **Step 5: Commit**

```powershell
git add accounts templates/base.html static/css/app.css
git commit -m "feat(accounts): add manager team directory"
```

### Task 7: Migrate Existing Campaign Authorization to Shared Policies

**Files:**
- Modify: `core/services.py`
- Modify: `core/views.py`
- Modify: `core/selectors.py`
- Modify: `core/tests.py` without overwriting existing user edits
- Modify: `templates/campaigns_list.html` only if role condition changes are required; preserve existing user edits
- Modify: other templates containing direct `owner`/`manager` comparisons found by `rg`

**Interfaces:**
- Consumes: `can_access_manager_workspace` and manager policy functions from Task 2.
- Produces: existing campaign behavior under the new `communications_manager` role.

- [ ] **Step 1: Add failing regression tests for manager/officer boundaries**

```python
def test_communications_manager_can_create_campaign(self):
    self.client.force_login(self.manager.user)
    response = self.client.post(reverse("campaign_create"), self.valid_campaign_data)
    self.assertEqual(response.status_code, 302)

def test_communications_officer_cannot_approve_strategy(self):
    self.client.force_login(self.officer.user)
    response = self.client.post(reverse("strategy_approve", args=[self.campaign.pk]))
    self.assertEqual(response.status_code, 403)
```

- [ ] **Step 2: Run focused tests and confirm legacy string checks fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests -v 2`  
Expected: FAIL where code still checks `owner`, `manager`, or `contributor`.

- [ ] **Step 3: Replace direct role strings with shared policies**

Run `rg -n 'owner|manager|contributor' core templates` and update authorization decisions. Preserve display copy and migration mappings where those words are not permission checks. Services must reject unauthorized mutations even if views are bypassed.

- [ ] **Step 4: Run core and accounts suites**

Run: `.\.venv\Scripts\python.exe manage.py test core accounts -v 2`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add core accounts templates
git commit -m "refactor(auth): centralize campaign role checks"
```

### Task 8: Seed Data, Documentation, and Full Verification

**Files:**
- Modify: `core/management/commands/seed_demo.py`
- Modify: `README.md`
- Modify: `.env.example`
- Create or modify: `accounts/admin.py`
- Create: `accounts/tests/test_seed.py`
- Modify: `core/admin.py` if duplicate registrations need removal

**Interfaces:**
- Consumes all prior tasks.
- Produces repeatable demo users for all five roles and documented environment behavior.

- [ ] **Step 1: Write failing repeatable-seed test**

```python
def test_seed_demo_creates_all_roles_without_duplicates(self):
    call_command("seed_demo", password="A-strong-test-password-2026")
    call_command("seed_demo", password="A-strong-test-password-2026")
    self.assertEqual(Membership.objects.values("role").distinct().count(), 5)
    self.assertEqual(Membership.objects.count(), 5)
```

- [ ] **Step 2: Run seed test and confirm missing roles fail**

Run: `.\.venv\Scripts\python.exe manage.py test accounts.tests.test_seed -v 2`  
Expected: FAIL because seed data still uses legacy roles.

- [ ] **Step 3: Update seed/admin/docs**

Document `COMMSOS_DEMO_AUTO_LOGIN=0` default, invitation-link behavior, role list, and the fact that email delivery/API endpoints are deferred. Register profiles and invitations with token hashes read-only and raw tokens absent.

- [ ] **Step 4: Run complete verification**

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
npm run build:css
git diff --check
```

Expected: all commands exit 0, all tests pass, no pending migrations, and no whitespace errors.

- [ ] **Step 5: Perform browser smoke test**

Start the server, then verify manager login, invitation creation, one-time acceptance, all role dashboards, directory scoping, deactivation denial for the last manager, and denial of manager routes to non-managers.

- [ ] **Step 6: Commit**

```powershell
git add README.md .env.example accounts core/management/commands/seed_demo.py
git commit -m "docs(accounts): document phase 1 identity workflows"
```

---

## Final Review Checklist

- [ ] Every Phase 1 acceptance criterion in the specification maps to a task above.
- [ ] Raw invitation tokens are never persisted or logged.
- [ ] All reads and writes are organization-scoped.
- [ ] Existing campaign operations use the new manager policy.
- [ ] Existing user modifications remain present in the final diff.
- [ ] No Django Ninja endpoint or deferred work/activity/inventory feature has been added prematurely.
