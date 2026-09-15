# Railway project layout

Same canvas as crypto marketplace (`cryptokars`): one GitHub repo, three processes, Postgres + Redis.

Config as Code (`railway.json` / `railway.toml`) is deprecated. This project uses Infrastructure as Code: `.railway/railway.ts` is the single source of truth.

| Canvas name | Process |
|---|---|
| **Postgres** | plugin · `DATABASE_URL` |
| **Redis** | plugin · `REDIS_URL` |
| **gunicorn api** | collectstatic + Gunicorn on `$PORT`; pre-deploy `bash ./build.sh` |
| **celery worker** | `celery -A config worker -Q main,celery -l info --autoscale 4,2` |
| **celery beat** | `celery -A config beat -l info` |

The root `Dockerfile` is for local Compose only (`sleep infinity`). Each GitHub service uses Railpack (`builder: "RAILPACK"` in `.railway/railway.ts`) so Railway does not run that image.

Requires Railway CLI 5.42.1+ (`railway config plan` / `railway config apply`) and `npm install` in `.railway/` so `railway/iac` resolves.

```bash
railway login
railway init --name agentradez
npm install --prefix .railway
railway config plan
railway config apply
railway domain --service "gunicorn api"
```
