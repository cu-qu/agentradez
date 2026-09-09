import {
  defineRailway,
  github,
  postgres,
  project,
  redis,
  service,
} from "railway/iac";

const REPO = "cu-qu/agentradez";

export default defineRailway((ctx) => {
  const db = postgres("Postgres");
  const cache = redis("Redis");
  const source = github(REPO, { branch: "main" });
  const stage = ctx.isEnvironment("stage");

  const env = {
    DJANGO_SETTINGS_MODULE: stage
      ? "config.settings.stage"
      : "config.settings.production",
    DEBUG: "false",
    SECRET_KEY: ctx.randomString("django-secret", 32),
    ALLOWED_HOSTS: ".up.railway.app",
    CSRF_TRUSTED_ORIGINS: "https://*.up.railway.app",
    DATABASE_URL: db.env.DATABASE_URL,
    REDIS_URL: cache.env.REDIS_URL,
    CELERY_BROKER_URL: cache.env.REDIS_URL,
    CELERY_RESULT_BACKEND: cache.env.REDIS_URL,
    CELERY_TASK_DEFAULT_QUEUE: "celery",
    FRONTEND_URL: "https://agentradez.com",
    CORS_ALLOWED_ORIGINS: "https://agentradez.com",
    DEFAULT_FROM_EMAIL: "Agentradez <noreply@example.com>",
  };

  const api = service("gunicorn api", {
    source,
    configFile: "railway_configs/api_server.toml",
    env,
  });

  const worker = service("celery worker", {
    source,
    configFile: "railway_configs/celery_worker.toml",
    env,
  });

  const beat = service("celery beat", {
    source,
    configFile: "railway_configs/celery_beat.toml",
    env,
  });

  return project("agentradez", {
    resources: [db, cache, api, worker, beat],
  });
});
