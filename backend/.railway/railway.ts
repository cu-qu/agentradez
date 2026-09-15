import {
  defineRailway,
  github,
  postgres,
  preserve,
  project,
  redis,
  service,
  volume,
} from "railway/iac";

/** Local Compose uses a sleep-forever Dockerfile; Railpack must own Railway builds. */
const railpack = { builder: "RAILPACK" } as const;

const env = {
  ADMIN_EMAIL: preserve(),
  ADMIN_PASSWORD: preserve(),
  ADMIN_USERNAME: preserve(),
  ALLOWED_HOSTS: preserve(),
  CELERY_BROKER_URL: preserve(),
  CELERY_RESULT_BACKEND: preserve(),
  CELERY_TASK_DEFAULT_QUEUE: preserve(),
  CORS_ALLOWED_ORIGINS: preserve(),
  CSRF_TRUSTED_ORIGINS: preserve(),
  DATABASE_URL: preserve(),
  DEBUG: preserve(),
  DEFAULT_FROM_EMAIL: preserve(),
  DJANGO_DB_HOST: preserve(),
  DJANGO_DB_NAME: preserve(),
  DJANGO_DB_PASSWORD: preserve(),
  DJANGO_DB_PORT: preserve(),
  DJANGO_DB_USER: preserve(),
  DJANGO_SETTINGS_MODULE: preserve(),
  EMAIL_PASSWORD_RESET_SUBJECT: preserve(),
  EMAIL_VERIFICATION_FRONTEND_PATH: preserve(),
  EMAIL_VERIFICATION_SUBJECT: preserve(),
  FRONTEND_URL: preserve(),
  JWT_ACCESS_LIFETIME_MINUTES: preserve(),
  JWT_REFRESH_DAYS: preserve(),
  METRICS_API_KEY: preserve(),
  PASSWORD_RESET_FRONTEND_PATH: preserve(),
  PORT: preserve(),
  POSTGRES_DB: preserve(),
  POSTGRES_PASSWORD: preserve(),
  POSTGRES_USER: preserve(),
  REDIS_URL: preserve(),
  SECRET_KEY: preserve(),
  X_PULLCALLS_API_CONSUMER_KEY: preserve(),
  X_PULLCALLS_API_SECRET: preserve(),
  X_PULLCALLS_BEARER_TOKEN: preserve(),
};

export default defineRailway(() => {
  const source = github("cu-qu/agentradez", {
    branch: "main",
    rootDirectory: "backend",
    checkSuites: false,
  });

  const cache = redis("Redis", { region: "europe-west4-drams3a" });
  cache.deploy = {
    startCommand:
      '/bin/sh -c "rm -rf $RAILWAY_VOLUME_MOUNT_PATH/lost+found/ && exec docker-entrypoint.sh redis-server --requirepass $REDIS_PASSWORD --save 60 1 --dir $RAILWAY_VOLUME_MOUNT_PATH"',
  };
  cache.networking = { privateNetworkEndpoint: "redis" };

  const db = postgres("Postgres", { region: "europe-west4-drams3a" });
  db.networking = { privateNetworkEndpoint: "postgres" };

  const redisVolume = volume("redis-volume-z3kJ", {
    alerts: { usage: { "100": {}, "80": {}, "95": {} } },
    allowOnlineResize: true,
    region: "europe-west4-drams3a",
    sizeMB: 50000,
  });
  const postgresVolume = volume("postgres-volume-dRwu", {
    alerts: { usage: { "100": {}, "80": {}, "95": {} } },
    allowOnlineResize: true,
    region: "europe-west4-drams3a",
    sizeMB: 50000,
  });

  const worker = service("celery worker", {
    source,
    build: railpack,
    start: "celery -A config worker -Q main,celery -l info --autoscale 4,2",
    deploy: { restartPolicyType: "ON_FAILURE" },
    replicas: { "europe-west4-drams3a": 1 },
    networking: { privateNetworkEndpoint: "upbeat-adaptation" },
    env,
  });

  const beat = service("celery beat", {
    source,
    build: railpack,
    start: "celery -A config beat -l info",
    deploy: { restartPolicyType: "ON_FAILURE" },
    replicas: { "europe-west4-drams3a": 1 },
    networking: { privateNetworkEndpoint: "athletic-communication" },
    env,
  });

  const api = service("api server", {
    source,
    build: railpack,
    start: "bash ./scripts/start_gunicorn.sh",
    preDeploy: "bash ./build.sh",
    healthcheck: "/api/health/",
    healthcheckTimeout: 300,
    deploy: { restartPolicyType: "ALWAYS" },
    replicas: { "europe-west4-drams3a": 1 },
    networking: { privateNetworkEndpoint: "agentictradingbackend" },
    env,
  });

  return project("Agentic Trading Backend", {
    resources: [worker, cache, beat, db, api, redisVolume, postgresVolume],
  });
});
