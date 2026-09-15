# CommsOS — Product Requirements and Technical Design

**Status:** Revised hackathon MVP specification

**Product promise:** From brief to campaign intelligence

**Stack:** Django, HTMX, Alpine.js, Tailwind CSS, PostgreSQL
**Primary user:** Communications manager in a small or medium-sized team

**Submission constraint:** The [official Devpost rules](https://ai-builders-hackathon-2026.devpost.com/rules) list the deadline as **15 September 2026 at 23:00 EDT**, equivalent to **16 September 2026 at 06:00 EAT**. They say submissions must be created during the hackathon period, which began **21 August 2026**. Confirm any pre-existing code/assets comply before submitting.

## 1. Product decision

CommsOS helps a communications team turn a campaign brief into an approved strategy and execution plan, track work and manually supplied performance, and apply evidence-based recommendations to the plan. The demo must show one complete, persisted loop:

**Brief → draft strategy → human approval → draft plan → human approval → content and tasks → performance → insight → proposed change → human approval → updated plan.**

AI output is always a proposal. Performance numbers are calculated from stored data, not invented by a model. Nothing is published to an external channel in the MVP.

### Success criteria

An evaluator with a test account can complete the loop above without developer intervention. The plan update survives a page refresh. Every displayed insight links to the metric rows and comparison period that support it. The whole journey works with the demo dataset if the AI provider is unavailable, while live generation clearly reports provider failures.

### Users and roles

| Role | MVP capability |
| --- | --- |
| Owner | Manage organization and members; all campaign actions |
| Manager | Create and approve strategy, plans, content, and recommendation actions; manage campaign data and assign tasks |
| Contributor | Edit assigned tasks and draft content; view campaigns in their organization |
| Viewer | Read campaigns, metrics, and reports |

The initial product supports one organization per user account. Membership and organization isolation are implemented now, even though billing, SSO, and advanced permissions are deferred. “Seats” are team memberships, not paid licenses. The owner alone manages membership; managers assign work only to active members. For the hackathon, seeded members suffice for demonstrating assignments. An owner-only add/deactivate-member flow is P1; if invitations are added, they must be single-use and expiring, without shared or emailed passwords.

## 2. Scope and release priorities

**P0 — required for the hackathon:** login, organization-scoped campaign CRUD, brief editing, structured AI strategy generation and approval, plan generation and approval, content items/tasks/calendar, contextual copy generation, manual performance entry, computed analytics, evidence-linked insight and recommendation, review-and-apply action, a focused campaign-specific explanation, and a simple report.

**P1 — if P0 is stable:** CSV performance import, general-purpose copilot, dashboard across campaigns, in-app alerts, section-level regeneration, weekly calendar, task assignment, richer report formatting, and undo of applied recommendations.

The implementation must follow [ENGINEERING.md](ENGINEERING.md), including service-layer permission checks, deterministic metric calculations, versioned approvals, and tests for cross-organization access and idempotent recommendation application.

**Post-MVP:** direct publishing, live platform analytics, WhatsApp or email delivery, brand knowledge base, forecasting, billing, SSO, native mobile, complex approval chains, and autonomous execution.

The official rules require a **project title and description, publicly accessible source repository (GitHub, GitLab, etc.), demo video (3–5 minutes recommended), documentation of the problem/solution/technology, and team member details**. The supplied overview additionally requests a **working product, completed submission form, and presentation deck of up to ten slides**, and says the video should be up to five minutes. Meet both sets of instructions. The official rules explicitly include students/recent graduates, developers, AI practitioners, designers, founders, open-source contributors, and technology enthusiasts; individuals and teams may participate. The student-only eligibility summary in the overview conflicts with the detailed rules, so verify the participant's account eligibility in Devpost rather than treating that summary as definitive.

For the demo, a 30-day plan means a bounded set of scheduled items across 30 days, not a post on every day. Seeded metrics are prominently labeled **Demo data**. A judge can replace them with manual entries.

## 3. Functional requirements and acceptance criteria

### F1. Campaign brief and lifecycle (P0)

The manager creates a campaign with name, objective, audience, geographic focus, start/end dates, channels, key issue, desired outcome, tone, and optional context. Organization comes from the active membership and cannot be selected from untrusted form input. Briefs can be saved incomplete; generating a strategy requires name, objective, audience, dates, and at least one channel. End date must be on or after start date. Campaign status is `draft`, `active`, `paused`, or `archived`; archiving does not delete historical data.

**Accept when:** a draft persists, invalid fields show inline errors, an authorized user can resume editing, and users from another organization get a 404 for the campaign and its children.

### F2. Strategy generation and approval (P0)

From a valid brief, the service requests structured fields: refined objective, primary/secondary audience, explicitly labeled audience assumptions, key/supporting messages, 3–5 content pillars, channel rationale, calls to action, proposed KPIs, and risks. Each KPI has a name, unit, direction, target, measurement source, and period. The result is stored as a new draft revision; it never overwrites an approved revision. A manager can edit any field and approve the draft. Regeneration creates a new revision and leaves the prior one accessible.

**Accept when:** invalid model output is rejected with a recoverable error, the original brief is retained, the user can edit and approve, and plan generation requires an approved strategy revision.

### F3. Execution plan, tasks, and calendar (P0)

The planner creates draft content items tied to one approved strategy revision and a content pillar, with channel, format, topic, objective, planned date, owner if known, and status. It may propose tasks and milestones, but may not invent real assignees. The manager reviews the proposal and applies it as one transaction. Users can add, edit, reschedule, and remove items. Task statuses are `todo`, `in_progress`, `review`, `done`, and `cancelled`; approval of a content item is tracked separately from task completion. The MVP calendar provides a month view and item detail, with an accessible list view.

**Accept when:** every planned item has a campaign, channel, date within the campaign range, and pillar; accepting the plan produces persisted items and tasks once; a repeated submit cannot duplicate them.

### F4. Content studio (P0)

From a content item, generate an editable draft of one of: social caption, short video script, carousel outline, creative brief, message/email copy, or website copy. The generation context includes the approved strategy revision, audience, tone, message, pillar, channel, and item objective. A creative brief includes asset format, intended audience, headline, copy, visual direction, CTA, required elements, and accessibility notes. Generated text is labeled and cannot be treated as published.

**Accept when:** the draft can be edited and saved, the source content item is linked, regeneration preserves previous versions, and a failed generation does not lose user edits.

### F5. Performance and analytics (P0)

Managers enter dated observations manually; P1 adds a documented CSV template and import. Each row records campaign, channel, optional content item, reporting date, source (`manual`, `csv`, `demo`), and applicable metrics: impressions, reach, engagements, clicks, conversions, views, shares, comments. Missing metrics remain `NULL`, not zero. Nonnegative integers only. The product defines **engagement rate = engagements / impressions × 100** and **CTR = clicks / impressions × 100**, displayed only when impressions are positive. Dashboard filters specify period and channel. Summing reach across observations is labeled **reported reach total**, since unique audience cannot be inferred.

**Accept when:** rates are reproducible from stored numerators/denominators and missing denominators display “Insufficient data.” For P1 CSV import, duplicate rows are identified by a stable import batch and row key, and invalid rows produce an error report.

### F6. Insights and recommendation actions (P0)

Deterministic analysis calculates period-over-period changes and channel/content-format comparisons. It records exact periods, sample sizes, metric definitions, and source observation IDs before asking AI to explain the results. The model may propose a hypothesis and an action, but the UI distinguishes **Observation**, **Possible explanation**, and **Recommendation**. A recommendation contains a preview of specific proposed item/task changes. The manager can approve or reject it. Apply checks the campaign's current plan revision; if the plan changed since proposal, the user must review a refreshed preview. Apply is atomic, idempotent, auditable, and produces a new plan revision. No external publishing occurs.

**Accept when:** an insight cites its underlying data, insufficient data yields no comparative claim, the preview lists every change, a contributor cannot apply it, and duplicate clicks create one revision only.

### F7. Campaign-aware copilot and report (P0)

The MVP provides a focused “Why did performance change?” explanation from the active campaign's saved metrics and insights. P1 expands this into a general-purpose copilot using a bounded context assembled from the approved strategy, plan, task summaries, metrics, and saved insights. It identifies the reporting period and states when data is missing. It cannot execute actions through chat. A report contains executive summary, objective, metric table, strongest/weakest observed content where comparable, evidence-backed insights, recommendations, completed work, and next actions. It displays source period and “Demo data” where applicable. MVP export is a printable HTML page; PDF is P1.

**Accept when:** the explanation only uses the active campaign's evidence, reported numbers match analytics queries, and the report remains readable without JavaScript. P1 copilot must also reject access to another organization's data.

### F8. Command center and alerts (P1)

Show active campaigns, overdue tasks, latest measured KPI state, and recent insights. Use explicit health components rather than a fabricated precision score. If a score is implemented, display its formula and mark components with missing data as unavailable, rather than scoring missing data as zero. In-app alerts can be generated for overdue tasks and measurable threshold breaches; email or push delivery is deferred.

## 4. Information architecture and UX

Primary navigation: **Command Center, Campaigns, Calendar, Tasks, Intelligence, Settings**. The copilot is a panel within a campaign, not a disconnected global chat. Campaign tabs: **Overview, Brief, Strategy, Plan, Content, Tasks, Performance, Insights, Report**. The most important calls to action are contextual: Generate strategy on Brief, Approve on Strategy, Apply plan on Plan, Add performance on Performance, and Review changes on a Recommendation.

All AI operations show queued/running/succeeded/failed states. Long jobs do not hold a browser request open. Forms retain values on validation errors. Keyboard focus moves to the result or error message after an HTMX update. Important actions have a server-rendered path that remains usable if Alpine.js is absent. Use clear labels for actual data, AI-generated drafts, and AI inference.

## 5. Technical architecture

### Stack responsibilities

| Layer | Choice and responsibility |
| --- | --- |
| Backend | Django modular monolith; domain logic in service modules, forms for validation, thin views |
| UI | Django templates for full pages and fragments; HTMX for targeted updates; Alpine.js for local UI state only; Tailwind for a consistent design system |
| Database | PostgreSQL as source of truth; Django migrations and constraints |
| AI | Provider adapter behind a service interface; structured JSON contracts and schema validation; provider/model configurable by environment |
| Jobs | Start with bounded synchronous generation if provider latency fits the host's request limit; add a background worker and persisted job state when measured latency requires it. Keep the provider call outside database transactions |
| Files | No media uploads in P0; CSV imports validated and processed with size/row limits |

Use Django's built-in authentication and CSRF protection. Server-side rendered HTML is the default; HTMX requests return fragments from the same permission-checked views. Alpine.js manages menus, dialogs, and local preview toggles, never authorization or canonical campaign state. Tailwind is compiled during build, not loaded from a CDN in production.

### Suggested Django apps

`accounts` (users, organizations, membership), `campaigns` (brief/strategy), `planning` (plan/content/tasks), `analytics` (observations/aggregates), `intelligence` (insights/recommendations), `ai` (provider/jobs/prompts), and `reports`. App boundaries express ownership; cross-app workflows live in explicit services, not model signals. Use the repository's existing structure if implementation has already begun.

### Request and job flow

1. Django validates the form, membership, and campaign state, then calls an AI service with a bounded, organization-scoped context, versioned prompt, schema, and timeout. The provider call happens outside a database transaction.
2. The service validates the response, records model/prompt version and metadata if available, and writes a draft revision. Provider errors return a safe user message and internal trace ID; existing edits remain intact.
3. HTMX updates the result area after completion. If generation exceeds the hosting request limit, move this same service behind a queue, persist `AIJob` state, and poll a status endpoint with bounded backoff.
4. Human approval uses a POST with CSRF, role check, expected revision, and transaction. Concurrent edits return a conflict and require review.

Never call the AI provider inside a database transaction. Set request timeouts, retry transient errors with a small cap, and use idempotency keys on generation and apply commands. Do not retry validation failures automatically.

### Core relational schema

All tables have UUID primary keys and UTC `created_at`/`updated_at`. Campaign-owned records carry `organization_id` as well as `campaign_id` where useful for scoped queries; enforce matching ownership in service validation and tests. Index `(organization_id, status)`, `(campaign_id, planned_date)`, `(campaign_id, due_at)`, and `(campaign_id, observed_on, channel)`.

| Model | Key fields and rules |
| --- | --- |
| Organization / Membership | name; `(organization_id, user_id)` unique; role enum |
| Campaign | organization FK, name, status, start/end, current strategy/plan revision; `end >= start` |
| CampaignBrief | campaign one-to-one, structured fields, `updated_by` |
| StrategyRevision | campaign FK, revision number unique per campaign, structured JSON validated against schema, state `draft/approved/superseded`, provenance, approved_by/at |
| PlanRevision | campaign FK, revision number, source strategy revision, state, created_by/applied_by; immutable snapshot or change set |
| ContentItem | campaign FK, pillar key, channel, format, topic, date, status, current plan revision, `created_from_recommendation` nullable |
| ContentDraft | content item FK, type, body/sections, revision, provenance, review status |
| Task | campaign FK, optional content item, assignee membership, title, due_at, priority, status |
| PerformanceObservation | campaign FK, optional content item, channel, observed_on, metrics, source, import batch/row key; nonnegative metric checks |
| Insight | campaign FK, period/comparison period, computed evidence JSON and observation references, narrative, confidence/limitations, generated_at |
| Recommendation | campaign FK, insight FK, status `proposed/rejected/applied/stale`, base plan revision, typed change set, applied_by/at |
| AIJob | organization/campaign FK, job type, status, idempotency key, prompt/schema/model versions, safe error, trace ID |
| AuditEvent | actor, organization/campaign, action, entity, before/after summary, timestamp |

JSON fields are appropriate for versioned AI drafts and a typed recommendation change set. Queryable business entities and performance metrics stay relational. Prevent dangling or cross-campaign references with foreign keys plus service-layer ownership checks. Use database `CHECK` and unique constraints for invariant fields; avoid relying only on form validation.

### Recommendation application contract

Allowed P0 operations: `create_content_item`, `reschedule_content_item`, `cancel_content_item`, and `create_task`. The model returns a proposal, not arbitrary field names or executable code. A validator checks operation type, item ownership, campaign dates, allowed channels, required fields, and a maximum change count. The preview renders from this validated change set. On apply, lock the campaign row, compare the base plan revision, apply all changes in one transaction, increment the revision, write an audit event, and mark the recommendation applied. A unique application key prevents replay. Undo, if added in P1, is a new compensating plan revision.

## 6. AI quality and trust

Compute statistics in Python/SQL and pass a compact evidence package to the model. Prompts treat campaign briefs, CSV contents, and retrieved text as untrusted data; they cannot override system instructions or request tool execution. Validate outputs against a schema and length limits. Store prompt/schema versions for reproducibility, while omitting secrets and unnecessary personal data from logs. Present interpretations as hypotheses, not verified causes. Do not infer individual-level traits from aggregate campaign data. Reject unsupported numerical claims by checking every cited metric against the evidence package.

Maintain a small evaluation set: a valid brief, incomplete brief, conflicting tone, sparse metrics, zero denominator, mixed demo/manual data, and stale recommendation. Review for schema validity, factual grounding, tone, usefulness, and safe failure. Keep deterministic fixtures for the live demo so the story works even if provider latency or rate limits intervene.

## 7. Security, privacy, and accessibility

Every query for organization-owned objects starts from the authenticated user's membership and active organization; object IDs alone never grant access. Enforce roles in service methods as well as views. Use Django CSRF tokens for all mutations, secure session cookies, HTTPS, environment-managed secrets, rate limits for login and AI endpoints, and safe escaping in templates. Do not render model output as trusted HTML. Set retention rules for AI request/response payloads and provide organization-level deletion/export procedures before real customer data is used. Back up PostgreSQL and test restore before production use.

Target WCAG 2.2 AA for core flows: semantic headings, labels/errors, visible focus, keyboard-operable dialogs, sufficient contrast, text alongside status colors, and accessible update announcements. HTMX fragment responses must preserve focus behavior and not duplicate element IDs.

## 8. Nonfunctional targets

These are MVP targets to validate, not claims of current performance: p95 server-rendered page response under 800 ms for a seeded organization with 20 campaigns and 5,000 observations; AI job submission under 1 second, with progress/status visible within 2 seconds; no lost writes on refresh or provider failure; initial database backup daily for deployed environments; and all P0 screens usable at 360 px width. AI generation completion time depends on the provider and is reported separately from page latency.

Instrument request latency, job duration/failure, generation cost, import failures, recommendation acceptance, and permission denials. Logs include a request/trace ID and exclude secrets and raw brief text by default.

## 9. Delivery and engineering practice

Use short, reviewable changes with migrations committed alongside models. Keep configuration in environment variables with a checked-in `.env.example`; never commit credentials. Pin dependencies with a lockfile. Use formatting/linting, type checking where practical, and CI for tests, migration checks, and asset build. Deploy from a reproducible build with separate development, test, and production settings. Run migrations as a release step and document rollback of code plus forward-only data migration recovery.

Test at three levels:

- **Domain tests:** metric formulas, sparse data, schema validation, campaign state transitions, recommendation diff validation and idempotency.
- **Integration tests:** organization isolation, role permissions, CSRF, concurrent approval conflict, transaction rollback, CSV import, AI provider failure, and report numbers.
- **Browser smoke test:** a test user completes the P0 journey on desktop and mobile width, including one keyboard-only path.

Mock the provider in automated tests; run a separate opt-in live-provider smoke test before the demo. Seed data through a repeatable management command that creates a clearly labeled demo organization/campaign and known observations. Do not put demo values into production migrations.

## 10. Delivery sequence

1. **Foundation:** Django project, PostgreSQL, auth/membership, Tailwind build, CI, organization-scoped campaign CRUD.
2. **Planning loop:** brief, strategy revisions, AI job adapter, approval, plan revisions, content/tasks/calendar.
3. **Measurement loop:** observations, deterministic aggregates, insight evidence, recommendation preview/apply/audit.
4. **Submission:** content studio and report, polish the single demo path, seed/demo script, accessibility and failure testing, public repository documentation, video, deck, and form.

With the stated deadline close, finish the complete brief-to-applied-recommendation path before expanding the surface area. CSV import, broad command center, alerts, and general-purpose copilot can move to P1 if they threaten a reliable working product. In that compressed delivery mode, F5 accepts manual performance entry and F7 accepts a campaign-specific “Why did performance change?” explanation tied to saved evidence; do not claim the deferred features in the submission.

Each milestone should produce a usable vertical slice. The main dependency is that analysis and recommendations require a stable observation schema and metric definitions; build these before polishing AI narratives.

## 11. Demo script and definition of done

Demo campaign: **Think Before You Click**, aimed at Kenyan university students aged 18–25 across TikTok, Instagram, WhatsApp, and a website. Create a draft brief; generate and edit a strategy; approve it; generate and apply a 30-day plan; open the calendar and task list; generate a TikTok scam-scenario script; import labeled demo observations; inspect a calculated channel/format comparison; review an evidence-linked recommendation to add two scenario videos; apply it; refresh to show persisted plan changes; ask the copilot about the comparison; print the report.

The submission is done when every P0 acceptance criterion passes, the demo can be repeated from a clean seed, permission and idempotency tests pass, AI downtime has a clear fallback, and a reviewer can trace one recommendation from source observations to an audited plan revision.

### Submission package

| Deliverable | Review standard |
| --- | --- |
| Working application | Publicly reachable or accompanied by clear local setup and demo credentials; core path works without developer narration |
| Public source repository | GitHub or GitLab; README with problem, architecture, prerequisites, environment variables, setup, seed command, tests, known limitations, and license; no committed secrets or private campaign data |
| Demo video (≤5 minutes) | Problem and user (about 30 seconds), brief-to-plan (about 90 seconds), content/measurement (about 60 seconds), evidence-to-applied-change (about 90 seconds), architecture/value (about 30 seconds) |
| Presentation deck (≤10 slides) | Problem, user, solution, product loop, key screens, technical architecture, AI workflow and trust, impact, roadmap, and demo/repository links |
| Devpost form | Accurate name, description, team details, working-product URL or access instructions, public code URL, video URL, and deck URL; test every link in a signed-out browser |

The overview gives judging weights of Innovation & Creativity **20%**, Technical Implementation **25%**, Problem Solving & Impact **25%**, UX & Design **15%**, and Presentation & Demo **15%**. The rules page lists related criteria without weights and also names **scalability and feasibility**. The submission should demonstrate each through observable behavior: a real workflow, deterministic evidence calculations, human-approved plan mutation, clear value to a communications manager, credible architecture, and a concise live demo. Avoid describing unbuilt roadmap items as implemented features.

## 12. Open decisions before customer launch

Select the AI provider and queue implementation based on deployment environment and cost; decide data residency and retention policies with prospective customers; confirm whether organizations need multiple workspaces; and validate exact channel KPI definitions with users. None of these should block the hackathon MVP, but they must be resolved before claiming enterprise readiness.
