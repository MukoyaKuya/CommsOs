# CommsOS engineering standards

These rules apply to implementation, including AI-generated code. Ship the smallest working vertical slice, but keep the boundaries and invariants below intact.

## Architecture and separation of concerns

- **Models** define persistent entities, relationships, constraints, and simple local behavior. They do not call AI providers, send email, or orchestrate multi-model workflows.
- **Forms and validators** validate untrusted input and produce field-level errors. Database constraints enforce invariants that must survive bypassing a form.
- **Service functions** own use cases such as `approve_strategy`, `apply_plan`, and `apply_recommendation`. They enforce permissions, state transitions, idempotency, and transactions. Views call services rather than duplicating business rules.
- **Selectors/query functions** assemble organization-scoped reads and analytics aggregates. No view fetches an organization-owned object by bare ID.
- **Views** authenticate, bind forms, call services/selectors, and render full templates or HTMX fragments. Keep them thin.
- **Templates** present server-provided state. They do not calculate campaign metrics or decide authorization. Alpine.js handles only transient UI behavior.
- **AI adapters** own provider API details, timeouts, response parsing, and error translation. Domain services consume validated structured data through an interface; they never depend on a provider SDK directly.

Prefer explicit functions and modules to a generic repository layer, signals, or a broad base-service hierarchy. Add abstraction where it protects a real boundary or removes repeated business logic. Keep dependency direction from web/UI to domain services to persistence/provider interfaces.

## Membership and access control

Use an `OrganizationMembership` model with a unique `(organization, user)` pair and role `owner`, `manager`, `contributor`, or `viewer`. **Owner** controls membership. **Manager** runs campaigns and approves strategy, plans, and recommendations. **Contributor** edits assigned work and draft content. **Viewer** reads. The MVP has no paid seat concept.

For the two-day build, seed demonstration members and implement a simple owner-only add/deactivate-member flow only after the core campaign loop is stable. If implemented, the owner selects an existing user or sends a single-use, expiring invite; never emails a password or lets an owner set another user's password. Email delivery and self-serve seat management can be deferred. Task assignees must be active members of the same organization. Protect both views and service functions, and test cross-organization access.

## Data integrity and state changes

- Use explicit status enums and documented transitions. Draft AI output cannot silently become approved.
- Version strategy and plan changes. Approval records actor and time. Stale submissions return a conflict instead of overwriting later edits.
- Apply recommendations in a transaction with row locking or an equivalent concurrency guard, expected plan revision, and unique idempotency key. Write an audit event in the same transaction.
- Keep metrics relational and calculate rates deterministically from stored numerators and denominators. Missing is distinct from zero.
- Use database foreign keys, uniqueness, checks, and migrations. Review migrations before applying them; avoid destructive schema changes close to submission.
- Use UTC storage and explicit campaign/reporting time zones when displaying dates.

## Security and AI trust

- Derive organization scope from the authenticated membership, never from a posted `organization_id`. Check object ownership for nested resources and mutations.
- Use Django sessions, CSRF protection, escaped templates, secure cookies in deployment, environment-managed secrets, and least-privilege database credentials.
- Treat briefs, imported data, and AI responses as untrusted input. Never render AI HTML as safe or allow model-provided code/SQL to execute.
- Validate structured AI responses against typed schemas and business rules before persistence. Record provenance, model/prompt/schema version, and a safe error state.
- Compute evidence before asking AI to interpret it. Label hypotheses, show sources and periods, and block unsupported numerical claims.
- Log request IDs and operational metadata, not secrets or full campaign briefs by default.

## Testing and quality gates

For each slice, run targeted unit/integration tests and then a browser smoke check. The minimum automated suite covers campaign/organization isolation, role checks, state transitions, metric formulas, missing/zero data, malformed AI output, provider failure, stale recommendation, double apply, and transaction rollback. Mock AI in CI; keep a separate opt-in live-provider check.

Format and lint Python and templates/JavaScript, run Django system checks and migration checks, and build Tailwind assets in CI. Pin dependencies and document exact startup commands. Keep `.env.example` safe; never commit credentials or production data. Use small commits after each working slice. Review AI-generated code and migrations before accepting them, especially permissions, query scoping, and generated SQL.

## Definition of engineering done

A feature is done when its acceptance criteria pass, failure states are understandable, permissions are enforced at the service boundary, data survives refresh, relevant tests pass, and the README reflects any new setup step. For the submission, the full demo journey must work from a clean seed on the deployed or documented review environment.
