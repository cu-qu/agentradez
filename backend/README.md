# Agentradez API

Automated copy-trading backend: users connect Alpaca or Robinhood, pick one Strategy and one Investment Tier, then the platform enters and manages option trades using that tier's rules.

Django 5.2 + DRF + JWT + Celery. Boots locally with Docker and on Railway with three services.

```bash
./scripts/start_agentradez.sh
```

Then:

| | |
|---|---|
| API | http://localhost:8001 |
| Swagger | http://localhost:8001/api/docs/ |
| ReDoc | http://localhost:8001/api/redoc/ |
| OpenAPI schema | http://localhost:8001/api/schema/ |
| Admin | http://localhost:8001/admin/ |
| Health | http://localhost:8001/api/health/ |

Stop with `./scripts/stop_agentradez.sh`.

Default admin (from `.env.example`): `admin` / `change-me`. Change it before any real deploy.

Web clients can fetch the OpenAPI document from `/api/schema/` with no auth (CORS allows `localhost:3000` and `localhost:5173`). Use that file with codegen (`openapi-typescript`, Orval, etc.). In Swagger, click **Authorize** and paste a JWT from `POST /api/auth/register/` or `POST /api/auth/token/` as `Bearer <access>`.

### Cursor: reopen in the Dev Container, then F5

The reopen toast only appears when this folder is opened or the window is reloaded. If you are already in the folder, run:

1. `Cmd+Shift+P` → **Dev Containers: Reset Don't Show Reopen Notification** (if you ever clicked Don't Show Again)
2. `Cmd+Shift+P` → **Developer: Reload Window**
3. Click **Reopen in Container** on the toast, or run **Dev Containers: Reopen in Container**

When the container is ready, **Run and Debug** → **Agentradez: API + Celery**. Django listens on port 8000 inside the container (Cursor forwards it). Postgres and Redis are already running as compose services.

---

## What you get

- Django 5.2 + DRF + SimpleJWT + drf-spectacular
- Custom `accounts.User` with **integer** primary keys (`BigAutoField`)
- Email verification + password reset (Resend via Anymail, console fallback)
- Celery worker + beat on Redis (signal distribution, position management, daily P&L)
- Split settings: `local` / `stage` / `production` / `test`
- WhiteNoise static files (production starts **without** object storage; gunicorn serves Django admin CSS from `STATIC_ROOT`)

Apps: `config`, `core`, `accounts`, `billing`, `trading`.

Seed data (`setup_base_data` / `seed_trading`) creates Conservative / Balanced / Aggressive tiers, the Copy Trade strategy, and a generic Research / Breakthrough strategy (no default sector or company universe). Copy Trade pulls signals from a configured source — X today, with chat groups planned later. The X source watches a configured account (`X_COPY_TRADE_HANDLE`) and turns option tweets into signals. Research / Breakthrough is configured per instance: sectors, news keywords, catalyst types, and watched companies. It scores confirmed catalysts and selects an options contract itself. Tier rules are stored as rows and can be edited by admins.

Broker adapters currently fill immediately for Alpaca (paper stub). Robinhood connections with OAuth tokens use the official Agentic Trading MCP (`get_accounts`, option quotes/orders).

## Auth API

| Method | Path |
|---|---|
| POST | `/api/auth/register/` |
| GET | `/api/auth/verify-email/?token=` |
| POST | `/api/auth/verify-email/resend/` |
| POST | `/api/auth/password-reset/` |
| POST | `/api/auth/password-reset/confirm/` |
| POST | `/api/auth/token/` |
| POST | `/api/auth/token/refresh/` |
| GET/PATCH | `/api/auth/me/` |
| GET/PATCH | `/api/auth/profile/` |
| GET | `/api/health/` |
| GET | `/api/schema/` and `/api/docs/` and `/api/redoc/` |
| | `/admin/` |

User ids in JSON are integers, not UUIDs.

## Billing API

Free is the default. Monthly and yearly unlock the `trading` feature (broker, assignment, positions, trades). Staff can grant a friend monthly/yearly by email — if they have not signed up yet, the grant is claimed on registration.

| Method | Path |
|---|---|
| GET | `/api/billing/plans/` |
| GET | `/api/billing/subscription/` |
| POST | `/api/billing/checkout/` |
| POST | `/api/billing/portal/` |
| POST | `/api/billing/webhooks/stripe/` |
| GET/PATCH | `/api/admin/billing/plans/` and `/api/admin/billing/plans/{id}/` |
| GET/POST | `/api/admin/billing/features/` |
| GET/PATCH | `/api/admin/billing/features/{id}/` |
| GET/POST | `/api/admin/billing/grants/` |
| POST | `/api/admin/billing/grants/{id}/revoke/` |

```bash
python manage.py grant_subscription friend@example.com --plan yearly
python manage.py grant_subscription friend@example.com --revoke
```

## Trading API (user)

| Method | Path |
|---|---|
| GET/POST | `/api/broker-connections/` |
| POST | `/api/broker-connections/robinhood/oauth/start/` |
| POST | `/api/broker-connections/robinhood/oauth/complete/` |
| GET | `/api/broker-connections/robinhood/oauth/callback/` |
| GET | `/api/broker-connections/{id}/accounts/` |
| POST | `/api/broker-connections/{id}/select-account/` |
| POST | `/api/broker-connections/{id}/disconnect/` |
| GET | `/api/strategies/` |
| GET | `/api/strategies/{id}/signals/` |
| GET | `/api/investment-tiers/` |
| GET/PUT | `/api/assignment/` |
| GET | `/api/positions/` |
| GET | `/api/trades/` |
| GET | `/api/trades/{id}/` |
| GET | `/api/performance/` |
| GET | `/api/notifications/` |
| POST | `/api/notifications/{id}/read/` |

## Trading API (admin)

| Method | Path |
|---|---|
| GET/POST | `/api/admin/strategies/` |
| GET/PATCH/DELETE | `/api/admin/strategies/{id}/` |
| GET | `/api/admin/strategies/{id}/posts/` |
| GET | `/api/admin/strategies/{id}/signals/` |
| POST | `/api/admin/strategies/{id}/lookback/` |
| GET | `/api/admin/strategies/{id}/events/` |
| POST | `/api/admin/strategies/{id}/research-poll/` |
| POST | `/api/admin/strategies/{id}/research-ingest/` |
| GET | `/api/admin/strategy-types/` |
| GET/POST | `/api/admin/user-groups/` |
| GET/PATCH/DELETE | `/api/admin/user-groups/{id}/` |
| GET/POST | `/api/admin/investment-tiers/` |
| GET/PATCH/DELETE | `/api/admin/investment-tiers/{id}/` |
| GET | `/api/admin/tier-usage/` |
| GET | `/api/admin/platform-stats/` |
| GET | `/api/admin/performance/by-tier/` |
| GET | `/api/admin/performance/by-strategy/` |
| GET | `/api/admin/users/` |
| GET | `/api/admin/users/{id}/` |
| POST | `/api/admin/users/assignment/` |
| GET/POST | `/api/admin/signals/` |
| GET | `/api/admin/signals/{id}/` |
| GET | `/api/admin/signal-decisions/` |
| GET/POST | `/api/admin/x-sources/` |
| GET/PATCH/DELETE | `/api/admin/x-sources/{id}/` |
| POST | `/api/admin/x-sources/{id}/poll/` |
| POST | `/api/admin/x-sources/{id}/ingest/` |
| POST | `/api/admin/x-parse/` |
| GET | `/api/admin/x-posts/` |
| GET | `/api/admin/x-posts/{id}/` |
| GET/POST | `/api/admin/watched-companies/` |
| GET/PATCH/DELETE | `/api/admin/watched-companies/{id}/` |
| POST | `/api/admin/research-parse/` |
| GET | `/api/admin/research-events/` |
| GET | `/api/admin/research-events/{id}/` |
| GET | `/api/admin/trades/` |
| GET | `/api/admin/trades/{id}/` |
| GET | `/api/admin/positions/` |

Creating a signal distributes it to every user assigned to that strategy, evaluates their tier (slippage, max positions, daily loss, sizing), and either skips or enters.

Staff (`is_staff`) can drive a frontend admin page from `/api/admin/...` without Django admin. Create a Copy Trade strategy and its X watcher in one request:

```json
POST /api/admin/strategies/
{
  "name": "Copy Alpha",
  "description": "Copies option entries from @alpha",
  "strategy_type": "copy_trade",
  "signal_source": "x",
  "visibility": "restricted",
  "allowed_user_ids": [2, 5],
  "allowed_group_ids": [1],
  "x_source": { "handle": "alpha", "is_active": true, "lookback_hours": 48, "poll_interval_seconds": 60 }
}
```

`visibility` is `public` (default; every authenticated user can pick it) or `restricted` (union of `allowed_user_ids` and members of `allowed_group_ids`). Omit `allowed_*` on PATCH to leave grants unchanged; send `[]` to clear. Restricted with empty lists is staff-only. `GET /api/strategies/` and `PUT /api/assignment/` honor this; staff force-assign does not. Existing assignments keep receiving signals if access is later revoked.

`GET /api/admin/strategy-types/` lists types the form can create. `DELETE` on a strategy, tier, or user group deactivates it (history is kept). Users pick active strategies they can access from `GET /api/strategies/`.

Research / Breakthrough is a generic catalyst strategy, not a healthcare product. `GET /api/admin/strategy-types/` includes presets (`any`, `healthcare`, `technology`, `deals`) you can copy into `research_config`. Sector, event types, keywords, and the company list are all inputs:

```json
POST /api/admin/strategies/
{
  "name": "Tech breakthroughs",
  "strategy_type": "research_breakthrough",
  "research_config": {
    "poll_interval_seconds": 60,
    "min_catalyst_score": 70,
    "sectors": ["tech", "semiconductor"],
    "enabled_event_types": ["breakthrough", "product_launch", "acquisition", "partnership"],
    "news_keywords": ["launch", "unveils", "acquisition", "breakthrough"],
    "require_confirmation": true,
    "otm_pct": "5.00",
    "min_dte": 14,
    "max_dte": 45
  },
  "watched_companies": [
    {"ticker": "NVDA", "name": "NVIDIA", "aliases": ["Nvidia"], "sector": "tech"}
  ]
}
```

Empty `sectors` / `enabled_event_types` / `news_keywords` means “all companies on this strategy” and a generic news query. Celery polls Google News for those names. A confirmed headline is classified, a slightly OTM contract in the 14–45 DTE window is selected, and that becomes a signal. Use `POST /api/admin/strategies/{id}/research-ingest/` or `python manage.py poll_research --ingest-headline "..."` to try a headline without waiting for RSS.

Copy Trade polls the watched X account on each source's `poll_interval_seconds` (default 60). Celery beat ticks every 15s and skips sources that are not due. Tweets matching option-entry formats such as `BTO $AAPL 200C 8/15 @ 2.50` become pending signals. Set `X_BEARER_TOKEN` and `X_COPY_TRADE_HANDLE` to enable live polling; otherwise use `POST /api/admin/x-sources/{id}/ingest/` or `python manage.py poll_x_account --ingest-text "..."`.

## Local

`./scripts/start_agentradez.sh` copies `.env.example` → `.env` if needed, starts Postgres + Redis, then the API / worker / beat containers, migrates, and seeds the admin user plus trading reference data.

Local host ports are **8001** (API), **5433** (Postgres), and **6380** (Redis) so this stack can run next to other Docker projects that already use 8000/5432/6379.

Without the script:

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec app python manage.py migrate --noinput
docker compose exec app python manage.py setup_base_data
```

Cursor/VS Code: compound launch **Agentradez: API + Celery** (`.vscode/launch.json`). Dev Container: `.devcontainer/`.

Tests (sqlite, no Docker):

```bash
DJANGO_SETTINGS_MODULE=config.settings.test python manage.py test
```

## Railway

Same canvas as crypto marketplace: one GitHub repo, three processes, Postgres + Redis.

```
                    ┌─────────────────────┐
                    │  gunicorn api       │◄── public domain
   GitHub repo ────►│  (Gunicorn + $PORT) │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ celery worker    │ │ celery beat      │ │ Postgres + Redis │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

| Service | Role | Config file (set on the service in Railway) |
|---|---|---|
| `gunicorn api` | web | `railway_configs/api_server.toml` — collectstatic + gunicorn on `$PORT`, `preDeployCommand` = `bash ./build.sh` |
| `celery worker` | worker | `railway_configs/celery_worker.toml` — `celery -A config worker -Q main -l info --autoscale 4,2` |
| `celery beat` | worker | `railway_configs/celery_beat.toml` — `celery -A config beat -l info` |
| Postgres | plugin | injects `DATABASE_URL` |
| Redis | plugin | injects `REDIS_URL` |

The root `Dockerfile` is local-only (`CMD sleep infinity`), same as crypto marketplace. Railway must **not** use it. Point each GitHub service at the toml file above (Settings → Config as Code → Config File Path).

`build.sh` (API pre-deploy): `pip install`, `migrate --noinput`, `collectstatic` for WhiteNoise, `setup_base_data`. The API image also collects static files at **build** and again on **start** (`scripts/start_gunicorn.sh`) so Django admin CSS is present in the running container. Worker and beat do not migrate.

### Bootstrap

Push this repo to GitHub, then:

```bash
railway login
./scripts/railway_agentradez.sh
```

(`--dry-run` prints the steps without calling the CLI.) The script applies `.railway/railway.ts` so the canvas matches crypto marketplace (Postgres, Redis, gunicorn api, celery worker, celery beat) and generates a public domain on **gunicorn api**.

If you create services in the dashboard instead: New → GitHub → `cu-qu/agentradez` three times, name them as in the table, set each Config File Path, add Postgres + Redis, then share `DATABASE_URL` / `REDIS_URL` into all three.

### Required env (all three services)

| Variable | Value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` |
| `SECRET_KEY` | new key (never reuse another product's) |
| `DEBUG` | `false` |
| `ALLOWED_HOSTS` | Railway hostname (and custom domain if any) |
| `CSRF_TRUSTED_ORIGINS` | `https://<railway-domain>` |
| `CORS_ALLOWED_ORIGINS` | frontend origin(s) |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` |
| `CELERY_BROKER_URL` | `${{Redis.REDIS_URL}}` |
| `CELERY_RESULT_BACKEND` | `${{Redis.REDIS_URL}}` |
| `FRONTEND_URL` | frontend origin used in email links and Robinhood OAuth return |
| `DEFAULT_FROM_EMAIL` | `Agentradez <noreply@example.com>` |
| `RESEND_API_KEY` | optional; console backend if unset |
| `ADMIN_USERNAME` / `ADMIN_EMAIL` / `ADMIN_PASSWORD` | seed superuser |
| `X_BEARER_TOKEN` | optional; X API v2 bearer token for copy-trade polling |
| `X_COPY_TRADE_HANDLE` | optional; X username the Copy Trade strategy watches |
| `PUBLIC_API_URL` | public API origin; on Railway, leave unset (uses `RAILWAY_PUBLIC_DOMAIN`) |
| `ROBINHOOD_OAUTH_REDIRECT_URI` | optional loopback callback only (default `http://localhost:8001/api/broker-connections/robinhood/oauth/callback/`). HTTPS hosts are ignored because Robinhood will not complete them |
| `ROBINHOOD_CLIENT_ID` | optional; reuse a previously registered OAuth client id (must match the loopback callback) |

Reference-variable syntax in the Railway dashboard is `${{PluginName.VARIABLE}}` (for example `${{Postgres.DATABASE_URL}}`). After the first deploy, set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` to the generated domain if the bootstrap script did not.

Laptop entrypoints default to `config.settings.local`. Railway must set `config.settings.production` (or `.stage`).

### Custom domain

Railway dashboard → `gunicorn api` → Settings → Networking → add domain. Then append that host to `ALLOWED_HOSTS` and `https://your.domain` to `CSRF_TRUSTED_ORIGINS`.

### Stage vs production

Two Railway environments, same repo:

- production → `DJANGO_SETTINGS_MODULE=config.settings.production`
- stage → `DJANGO_SETTINGS_MODULE=config.settings.stage`

Fork/create a `stage` environment (`railway environment new stage` or Railway MCP `create_environment`). Both use WhiteNoise; neither requires R2.

### Migrations

They run on **gunicorn api** only, via `preDeployCommand` → `bash ./build.sh`. Worker and beat do not migrate.

## Copying this boilerplate for a new product

1. Duplicate the repo.
2. Replace `agentradez` / `Agentradez` / `agentradez` / `cu-qu/agentradez`.
3. Rename `scripts/start_agentradez.sh`, `scripts/stop_agentradez.sh`, `scripts/railway_agentradez.sh`.
4. Generate a new `SECRET_KEY`. Do not copy production secrets from another project.
5. Boot with `./scripts/start_<slug>.sh`, fill **[NEW_PROJECT_BUILD.md](NEW_PROJECT_BUILD.md)** with the idea plan, and paste that file into a new agent chat. The agent should add domain apps on top of `config` / `core` / `accounts` — not replace them.
