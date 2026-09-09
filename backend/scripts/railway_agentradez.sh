#!/usr/bin/env bash
# Create the agentradez Railway canvas: Postgres, Redis, gunicorn api,
# celery worker, celery beat. Source of truth is .railway/railway.ts.
#
# Prerequisites:
#   1. This repo is on GitHub (default: cu-qu/agentradez)
#   2. Railway CLI is installed and logged in (`railway login`)
#   3. The Railway GitHub app can read that repo
#
# Usage:
#   ./scripts/railway_agentradez.sh
#   ./scripts/railway_agentradez.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT_DISPLAY_NAME="agentradez"
API_SERVICE="gunicorn api"
DRY_RUN=0

if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
fi

run() {
  echo "+" "$@"
  if [ "$DRY_RUN" -eq 0 ]; then
    "$@"
  fi
}

echo "Railway bootstrap for ${PROJECT_DISPLAY_NAME}"
echo "  Layout: Postgres, Redis, gunicorn api, celery worker, celery beat"
echo "  IaC:    .railway/railway.ts"
echo

if [ "$DRY_RUN" -eq 0 ] && ! command -v railway >/dev/null 2>&1; then
  cat <<EOF
Railway CLI not found. Install it, then re-run this script:

  npm i -g @railway/cli
  railway login

Or from Cursor, authenticate the Railway MCP and apply .railway/railway.ts.
EOF
  exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "Would run: railway login (if needed)"
  echo "Would run: railway init --name ${PROJECT_DISPLAY_NAME}  (if unlinked)"
  echo "Would run: railway config apply"
  echo "Would run: railway domain --service ${API_SERVICE}"
  exit 0
fi

if ! railway whoami >/dev/null 2>&1; then
  echo "Not logged in. Opening Railway login..."
  railway login
fi

if [ ! -f .railway/config.json ] && [ ! -f railway.json ]; then
  railway init --name "${PROJECT_DISPLAY_NAME}" || railway link
fi

echo "Applying .railway/railway.ts..."
railway config apply

echo "Generating a public domain on ${API_SERVICE}..."
railway domain --service "${API_SERVICE}" || true

cat <<EOF

Railway canvas should now match:

  Postgres          plugin   DATABASE_URL
  Redis             plugin   REDIS_URL
  gunicorn api      web      collectstatic + gunicorn on \$PORT, pre-deploy ./build.sh
  celery worker     worker   celery -A config worker -Q main,celery
  celery beat       worker   celery -A config beat

Next:
  - Set CORS_ALLOWED_ORIGINS and FRONTEND_URL to your frontend origin
  - Set ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD, then redeploy gunicorn api
  - Set RESEND_API_KEY if you want real email
  - For stage: railway environment new stage
    (DJANGO_SETTINGS_MODULE becomes config.settings.stage in that environment)

EOF
