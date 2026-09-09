#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "Starting Postgres and Redis..."
docker compose up -d --build db redis

echo "Waiting for Postgres and Redis to be healthy..."
for _ in $(seq 1 60); do
  db_ok="$(docker compose ps --format json db 2>/dev/null | grep -c '"Health":"healthy"' || true)"
  redis_ok="$(docker compose ps --format json redis 2>/dev/null | grep -c '"Health":"healthy"' || true)"
  if docker compose exec -T db pg_isready -U postgres -d agentradez >/dev/null 2>&1 \
    && docker compose exec -T redis redis-cli ping >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! docker compose exec -T db pg_isready -U postgres -d agentradez >/dev/null 2>&1; then
  echo "Postgres did not become healthy in time." >&2
  exit 1
fi
if ! docker compose exec -T redis redis-cli ping >/dev/null 2>&1; then
  echo "Redis did not become healthy in time." >&2
  exit 1
fi

echo "Starting app, Celery worker, and Celery beat..."
docker compose up -d --build app celery celery-beat

echo "Running migrations..."
docker compose exec -T app python manage.py migrate --noinput

echo "Collecting static files (WhiteNoise)..."
docker compose exec -T app python manage.py collectstatic --noinput

echo "Seeding base data..."
docker compose exec -T app python manage.py setup_base_data

if [ ! -f NEW_PROJECT_BUILD.md ]; then
  echo "Missing NEW_PROJECT_BUILD.md (product idea plan + agent prompt)." >&2
fi

cat <<'EOF'

Agentradez API is up
API:     http://localhost:8001
Docs:    http://localhost:8001/api/docs/
ReDoc:   http://localhost:8001/api/redoc/
Schema:  http://localhost:8001/api/schema/
Admin:   http://localhost:8001/admin/
Health:  http://localhost:8001/api/health/

Host ports are 8001 (API), 5433 (Postgres), 6380 (Redis) so this stack
can run alongside other local Docker projects using 8000/5432/6379.

Web clients: fetch OpenAPI from /api/schema/ (no auth).
Authorize in Swagger with a JWT from POST /api/auth/token/ or /api/auth/register/.
Admin login: admin / change-me (from .env)

EOF
