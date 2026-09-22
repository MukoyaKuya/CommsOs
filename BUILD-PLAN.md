# CommsOS — two-day AI-assisted build plan

**Submission deadline in the official rules:** 15 September 2026, 23:00 EDT / 16 September 2026, 06:00 EAT. Submit with a buffer; do not plan to finish at the deadline.

## The product to ship
 
One organization, one demo campaign, and one complete persisted path:
 
1. Create/edit the campaign brief.
2. Generate a structured strategy draft with AI, edit it, approve it.
3. Generate a small dated content plan from that approved strategy; review and apply it.
4. Generate one campaign-specific content draft from a plan item.
5. Enter or seed performance observations, showing source labels.
6. Calculate a genuine format/channel comparison from the observations.
7. Generate an evidence-linked recommendation and show its proposed changes.
8. Approve it, update the plan transactionally, refresh, and show the new item(s).
9. Show a short printable campaign report.

This is the judging story. Everything else is optional.

## Build decisions for speed

- Use a Django modular monolith with server-rendered templates, HTMX fragments, Alpine.js only for dialogs/local state, Tailwind compiled locally, and PostgreSQL.
- Use Django authentication. Support a single organization in the demo but store `organization_id` and check membership on every campaign query. Seed the demo organization and user with a management command.
- Seed an owner, manager, and contributor for the demo. Owner-only membership management is optional after the core loop; do not build billing or password-sharing flows. Follow [ENGINEERING.md](ENGINEERING.md) for service boundaries and access checks.
- Keep AI behind one provider adapter with two structured operations: `generate_strategy` and `generate_plan`; add `generate_content` and `explain_evidence` only after the first two work. Validate JSON responses before persistence.
- For a two-day demo, a synchronous AI call with a strict timeout and clear retry state is acceptable if jobs regularly complete within the hosting request limit. If not, use a background worker. Do not spend the first day building generic job infrastructure.
- Use a deterministic analytics function for rates and comparisons. AI writes explanations from those computed results; it never supplies metric values.
- Use one `Recommendation` change type initially: create one or two new dated content items. Preview the exact items and apply under a database transaction with a unique idempotency key.
- Use a seeded demo dataset with clearly labeled provenance. It must be reproducible from a management command and visible in the app.
- Pick and lock versions of dependencies at setup time. Keep secrets in environment variables and a safe `.env.example`.

## Day 1 — make the loop real

| Order | Deliverable | Exit check |
| --- | --- | --- |
| 1 | Project, PostgreSQL, auth, base UI, migration/seed commands | App starts from README; login works |
| 2 | Campaign brief form and organization-scoped detail page | Create/edit/refresh persists; cross-org access fails |
| 3 | Strategy generator, JSON validation, draft editor, approval | Approved revision persists; provider failure preserves brief |
| 4 | Plan generator, content-item model, review/apply, calendar list | Items link to strategy and survive refresh |
| 5 | Manual/seed observations and deterministic comparison | Displayed rates match stored counts, including zero-denominator handling |

Stop Day 1 only when the first five steps work through the browser. Styling beyond clear layout can wait.

## Day 2 — close the loop and submit

| Order | Deliverable | Exit check |
| --- | --- | --- |
| 1 | Evidence-linked insight and recommendation preview/apply | Approval changes plan once; refresh proves persistence |
| 2 | Content draft and printable report | Both reflect the approved campaign and real metric period |
| 3 | Focused tests and smoke run | Tenant isolation, math, JSON validation, stale/double apply, provider failure pass |
| 4 | UX polish | One complete keyboard path, mobile width, clear loading/error states |
| 5 | Public repository and deployment/review path | Signed-out reviewer can access code and app or follow documented setup |
| 6 | Record ≤5-minute demo, make ≤10-slide deck, complete Devpost form | Links tested signed out; submission confirmation captured |

Reserve the final several hours for deployment, recording, upload, and submission. Do not start new features during that period.

## Cut line

If time slips, cut in this order: dashboard, alerts, weekly calendar, CSV import, multi-user assignments, general chat copilot, PDF export, multiple content formats, section-level regeneration, and advanced health scoring. Keep the approved strategy → plan → measured evidence → approved plan change loop intact. A simple month/list calendar and one content format are enough to demonstrate it.

## AI coding workflow

Give the coding assistant one vertical slice at a time with: target files, behavior, acceptance checks, and explicit instruction to run the relevant tests. Review generated migrations, security-scoped querysets, provider error handling, and diff before moving on. Avoid parallel edits to the same files. Commit after each working slice so a failed late change can be rolled back. Keep a short `KNOWN-LIMITATIONS.md` and describe demo data honestly.

## Minimum verification before recording

- Fresh clone/setup, migrations, seed, login, and full demo path work.
- Cross-organization URL access is denied.
- Invalid AI JSON and provider timeout leave existing data unchanged.
- Every metric and comparative percentage is calculated from stored observations.
- Double-clicking Apply creates one change; stale recommendations cannot overwrite later edits.
- Browser refresh preserves approvals and applied changes.
- No secrets, private data, or local-only paths appear in the public repository.
- Video and deck links work without being signed in.

## Submission contents

The [official rules](https://ai-builders-hackathon-2026.devpost.com/rules) require a title/description, public source repository, demo video (3–5 minutes recommended), documentation, and team details. The overview supplied for this project additionally asks for a working product and a deck of up to ten slides. Submit all of them. The rules say work must be created during the hackathon period beginning 21 August 2026; verify provenance of anything reused.
