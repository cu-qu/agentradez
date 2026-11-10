# Agentradez

AI agent trading: connect a broker, pick a strategy and risk tier, and Agentradez submits the orders.

The original `agentic_trading_backend` and `agentic_trading_web` repos are unchanged. This repo is the combined copy to work from.

- Public site: `agentradez.com`
- Primary users: traders connecting Alpaca or Robinhood, staff configuring strategies and tiers

## Layout

| Path | What |
|---|---|
| `backend/` | Django 5.2 + DRF + JWT + Celery. Accounts, billing (Stripe subscriptions), trading. Railway: api / worker / beat + Postgres + Redis. |
| `web/` | Next.js App Router client, including marketing (home, how it works, strategies, terms, homepage drafts) |
| `agent_artifacts/` | Agent outputs, PR QA plans, issue recording, growth notes, issue resolutions |
| `PRODUCT_PLAN.md` | Product snapshot for this combined folder |

Product Django apps: `backend/trading/` and `backend/billing/`. Auth stays in `backend/accounts/` (integer PKs, email verify, password reset, JWT).

Payments: Stripe **subscription** (`backend/billing/`, `/api/billing/`).

## Local

Open this folder in Cursor. **Run and Debug** → **All services** starts Django, Next.js, Celery, and Stripe listen together (`stopAll: true`).

### Full stack (Docker API + host web)

```bash
cd backend
./scripts/start_agentradez.sh
```

In another terminal:

```bash
cd web
cp .env.example .env.local   # first time only
npm install
npm run dev
```

| | |
|---|---|
| Web (marketing + app) | http://localhost:3000 |
| How it works | http://localhost:3000/how-it-works |
| Strategies | http://localhost:3000/strategies |
| Terms | http://localhost:3000/terms |
| Homepage drafts | http://localhost:3000/home-pages |
| API | http://localhost:8001 |
| Docs | http://localhost:8001/api/docs/ |
| Admin | http://localhost:8001/admin/ (`admin` / `change-me`) |
| Health | http://localhost:8001/api/health/ |

Host ports for the API stack are **8001** (API), **5433** (Postgres), and **6380** (Redis) so this can run next to other Docker projects on 8000/5432/6379. Stop the API with `./scripts/stop_agentradez.sh`. Stop the web with `cd web && ./scripts/stop_frontend.sh` if you started it via Compose.

### Dev Container (API + web)

From this repo root in Cursor / VS Code, **Reopen in Container** and pick **agentradez**. That one container starts Postgres, Redis, Django, and Next.js (ports **8002** / **3000** so it will not fight other stacks for 8000 / 5432 / 6379):

| | |
|---|---|
| API | http://localhost:8002 |
| Docs | http://localhost:8002/api/docs/ |
| Admin | http://localhost:8002/admin/ (`admin` / `change-me`) |
| Web | http://localhost:3000 |

The web app calls the API at `http://localhost:8002`.

Optional single-app containers are still in the picker: **agentradez backend** and **agentradez web**. You can also open `backend/` or `web/` on its own and reopen that folder in its container.

## Production

`.github/workflows/image.yml` builds `ghcr.io/cu-qu/agentradez-api` and `ghcr.io/cu-qu/agentradez-web`. `cu-qu/cuqulabs-core-services` deploys those images. The public names are `agentradez.com`, `www.agentradez.com`, and `api.agentradez.com`. Railway and Vercel are not the production host.

## Payments

Stripe **subscription** (`backend/billing/`, `/api/billing/`). Free is the default. Monthly and yearly unlock the `trading` feature.

Required backend env: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_MONTHLY`, `STRIPE_PRICE_YEARLY`.

Webhook: `https://api.agentradez.com/api/billing/webhooks/stripe/`

```bash
python manage.py grant_subscription friend@example.com --plan yearly
```

## Marketing

Public pages live in `web/src/app/` and share `MarketingShell` / `HomeNav`:

- `/` — live homepage
- `/how-it-works` — four-step product story
- `/strategies` — public strategy explainers
- `/terms` — terms and risk disclosure
- `/home-pages` plus `/home-page-1` … `/home-page-5` — homepage drafts (noindex)

Vercel Analytics is in `web/src/app/layout.tsx`. Enable Web Analytics on the Vercel project after the first deploy.

## Agent artifacts

Use `agent_artifacts/` for:

- `product_growth/` — experiments, launch, metrics
- `product_improvements/` — follow-ups and issue resolutions
- `issue_recording/` — bugs and incidents
- `pr_qa_plans/` — QA checklists
- `agent_outputs/` — agent run notes
