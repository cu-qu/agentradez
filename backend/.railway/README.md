# Railway project layout

Same canvas as crypto marketplace (`cryptokars`): one GitHub repo, three processes, Postgres + Redis.

| Canvas name | Config file | Process |
|---|---|---|
| **Postgres** | plugin | `DATABASE_URL` |
| **Redis** | plugin | `REDIS_URL` |
| **gunicorn api** | `railway_configs/api_server.toml` | collectstatic + Gunicorn on `$PORT` |
| **celery worker** | `railway_configs/celery_worker.toml` | `celery -A config worker -Q main` |
| **celery beat** | `railway_configs/celery_beat.toml` | `celery -A config beat` |

Each GitHub service **must** use that Config File Path. The root `Dockerfile` is for local Compose only (`sleep infinity`). Without the toml file, Railway would run that image and the service would sit idle.

```bash
railway login
railway init --name agentradez
railway config apply
railway domain --service "gunicorn api"
```
