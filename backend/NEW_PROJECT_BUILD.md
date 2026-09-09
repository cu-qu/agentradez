# New product build prompt

Use this after the boilerplate is running. Fill in **Idea plan**, then paste this whole file into a **new agent chat** in this repo.

The agent must extend **this** Django API starter. Do not clone a new repo. Do not strip auth, Celery, Docker, or Railway.

---

## How to use

1. Boot the skeleton: `./scripts/start_agentradez.sh`
2. Fill every `FILL IN` block below (replace the angle-bracket examples).
3. Open a new Cursor agent chat with this workspace.
4. Paste this file as the user message.

---

You are implementing a new product **on top of Agentradez** (this repo).

This is already a working Django 5.2 + DRF + JWT + Celery + Postgres + Redis API, deployable locally (Docker Compose) and on Railway (api / worker / beat). It has **no product domain** yet — only platform skeleton.

Your job: turn the idea plan into real apps, models, APIs, admin, tests, and Celery tasks **without breaking the skeleton**.

══════════════════════════════════════
FILL IN — idea plan
══════════════════════════════════════

- PRODUCT_SLUG:          <e.g. inventory>         # python/app-safe: snake_case
- PRODUCT_DISPLAY_NAME:  <e.g. Acme Inventory>
- ONE_LINER:             <one sentence: who it is for and what it does>
- PRIMARY_USERS:         <e.g. owner, staff, customer>
- OUT OF SCOPE (v1):     <what you will not build yet>

### Problem and v1 outcome

<What hurts today, and what a user can do when v1 ships.>

### Domain models (integer PKs only)

List concrete Django models. Every PK is an implicit `BigAutoField`. No UUID primary keys.

| Model | Belongs to | Fields (sketch) | Notes |
|---|---|---|---|
| <e.g. Item> | <app> | <name, owner FK, …> | <soft-delete? unique?> |

Relationships (1:1, FK, M2M) and who owns the row:

<e.g. User 1:N Item; Item N:M Tag>

### API surface (v1)

Prefix under `/api/`. Reuse existing auth; do not reimplement JWT.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| <GET> | </api/…> | <JWT / admin / public> | <…> |

### Celery

Keep `accounts.ping` as the example. Add product tasks on queue `"main"`. Beat schedule may gain jobs; do not remove worker/beat services.

| Task | Trigger | Queue | What it does |
|---|---|---|---|
| <e.g. product.digest> | <beat hourly / on-save> | main | <…> |

### Admin, emails, extra

- Django admin: <which models, list_display>
- Emails: <none / which templates besides verify + password reset>
- Reference data / management commands: <none / seed_X>
- Frontend assumption: <SPA at FRONTEND_URL / none>

### Non-goals

<e.g. no billing, no social login, no mobile-specific APIs>

══════════════════════════════════════
KEEP (do not rip out)
══════════════════════════════════════

- `config/` — settings split (local / stage / production / test), celery, wsgi/asgi, urls
- `core/` — SoftDeleteModel, health check, exception logger, `setup_base_data`
- `accounts/` — User (integer pk), UserProfile, register / verify-email / password-reset / JWT / me / profile
- Celery worker + beat on Redis; compose commands stay `-A config`
- Docker Compose, Dev Container, `.vscode` launch/tasks, branded start/stop/railway scripts
- Railway: three services + Postgres + Redis; gunicorn binds `$PORT`; WhiteNoise (production boots without R2)
- OpenAPI at `/api/docs/` and `/api/schema/`; `@extend_schema` on new views
- `DEFAULT_AUTO_FIELD = django.db.models.BigAutoField`

Auth routes stay:

- `POST /api/auth/register/`
- `GET /api/auth/verify-email/?token=`
- `POST /api/auth/verify-email/resend/`
- `POST /api/auth/password-reset/`
- `POST /api/auth/password-reset/confirm/`
- `POST /api/auth/token/` and `/token/refresh/`
- `GET/PATCH /api/auth/me/` and `/api/auth/profile/`
- `GET /api/health/`
- `/admin/`

══════════════════════════════════════
IMPLEMENT
══════════════════════════════════════

1. **Rebrand only if the idea plan says this copy is the new product**  
   If PRODUCT_DISPLAY_NAME differs from "Agentradez", rename slug/display strings, script filenames, compose DB name, Celery app name, spectacular TITLE, and README. If this repo is still a generic starter being specialized, do that rename as part of this work.

2. **New Django app(s)** named from PRODUCT_SLUG (and extra apps if the plan needs them).  
   Register in `INSTALLED_APPS` and `config/urls.py` under `/api/`.  
   Fresh migrations. Do not rewrite accounts migrations.

3. **Models**  
   Integer PKs only (implicit BigAutoField). Use `core.models.SoftDeleteModel` where the plan wants soft delete.  
   User FKs point at `settings.AUTH_USER_MODEL`.  
   No UUID primary keys. Do not import `uuid` for ids.

4. **API**  
   DRF viewsets/views + serializers + urls. JWT auth unless the row in the plan says public.  
   `@extend_schema` with tags (add product tags; keep Auth, Profile, Reference).  
   Update `SPECTACULAR_SETTINGS` DESCRIPTION + TAGS so `/api/docs/` lists the new endpoints.  
   Follow `.cursor/rules/openapi-schema.mdc`.

5. **Celery**  
   Tasks in the new app’s `tasks.py`, `queue="main"`.  
   Register beat entries in `config/celery.py` only for jobs listed in the plan. Keep `accounts.ping`.

6. **Admin + seeds**  
   Register models in admin.  
   `setup_base_data` may call extra seed commands **after** `create_admin_user`. Do not hardcode personal admin accounts; keep `ADMIN_*` env vars.

7. **Tests**  
   API tests for the new endpoints (auth required where planned). Integer ids. No UUID assertions. Existing accounts tests must still pass.

8. **Infra**  
   Do not add a second PaaS. Do not require R2 to boot. Do not change gunicorn `$PORT` or the three Railway services unless the plan explicitly needs a fourth process.  
   Local boot remains `./scripts/start_<slug>.sh` (or the current start script if you have not renamed yet).

══════════════════════════════════════
QUALITY
══════════════════════════════════════

- `python manage.py check` passes
- `DJANGO_SETTINGS_MODULE=config.settings.test python manage.py test` passes
- `/api/docs/` matches the new endpoints
- User.id and all new model ids are bigint / int in JSON
- No leftover marketplace/domain from other products
- Production settings still start without object storage

When done, list: new apps, models, API routes, Celery tasks, and what stayed untouched in the skeleton.
