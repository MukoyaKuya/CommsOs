# CommsOS

CommsOS is a Django application for communications teams to turn a campaign brief into an approved strategy and plan, record performance, and apply an evidence-linked recommendation. The demo mode uses clearly labeled deterministic AI-style drafts; a configured AI provider enables live generation. No external publishing occurs.

The product and technical requirements are in [PRD.md](PRD.md), the delivery plan in [BUILD-PLAN.md](BUILD-PLAN.md), and implementation rules in [ENGINEERING.md](ENGINEERING.md).

## Stack

Django 6, server-rendered templates, HTMX, Alpine.js, Tailwind CSS, and PostgreSQL. SQLite is a local fallback when PostgreSQL variables are absent; deployment should use PostgreSQL. Provider calls are isolated in `core/ai.py`, workflows in `core/services.py`, scoped reads in `core/selectors.py`, and deterministic calculations in `core/analytics.py`.

## Local setup

Use Python 3.14+ and Node.js 24+. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm ci
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo --password 'choose-a-throwaway-demo-password'
npm run build:css
python manage.py runserver
```

The demo accounts are `demo_owner` (Communications Manager), `demo_manager` (Communications Officer), `demo_contributor` (Support Staff), `demo_intern`, and `demo_viewer`, all with the password passed to `seed_demo`. Each account has one fixed role and belongs to one organization. Use a throwaway password and never expose demo credentials in a real deployment. Visit `http://127.0.0.1:8000/`.

Communications Managers can open **Team Directory** to create a single-use invitation link for a staff member. Links expire after 72 hours and are shown only when created; email delivery is deferred. Set `COMMSOS_DEMO_AUTO_LOGIN=1` only for local demonstrations that intentionally bypass login. It is disabled by default and ignored when `DJANGO_DEBUG=0`.

For PostgreSQL, set `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT` in `.env`, then rerun migrations/seed. Create the database and least-privilege user separately. Do not commit `.env`.

Alternatively, with Docker Desktop running, set a throwaway `POSTGRES_PASSWORD` and `DJANGO_SECRET_KEY` in `.env`, then run `docker compose up --build`. In another terminal run `docker compose exec web python manage.py migrate` and `docker compose exec web python manage.py seed_demo --password 'choose-a-throwaway-demo-password'`. The compose file is for local development and runs Django with debug enabled. For public hosting, set `DJANGO_DEBUG=0`, a strong secret, actual host names, trusted CSRF origins, PostgreSQL, HTTPS, and `DJANGO_TRUST_PROXY_HTTPS=1` only behind a trusted TLS-terminating proxy.

To use live AI generation, set `AI_MODE=openai`, `OPENAI_API_KEY`, and optionally `OPENAI_MODEL` / `OPENAI_BASE_URL`. The adapter expects a chat-completions-compatible JSON endpoint. In `AI_MODE=demo`, strategy, plan, copy, and explanations are deterministic demonstrations and labeled as demo provenance. Performance figures still come from stored observations.

## Test and build

```powershell
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
npm run build:css
```

## Demo path

Sign in as `demo_manager`, open **Think Before You Click**, generate and edit the strategy, approve it, generate/apply a plan, generate copy for an item, inspect the labeled demo observations, analyze performance, preview/apply the recommendation, refresh, and open the printable report. The seed command is repeatable and does not duplicate observations.

## Current limits

The app is an MVP. It has a simple campaign workspace and list calendar rather than a full calendar grid. Team members are seeded; self-service invitations and task assignment are deferred. AI generation runs within a bounded request; a background worker is needed if deployment request limits or provider latency demand it. Demo insights are based on seeded aggregate performance, not live social integrations. PDF export, CSV import, and external publishing are deferred.
