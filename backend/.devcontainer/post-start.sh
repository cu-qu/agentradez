#!/usr/bin/env bash
set -euo pipefail
cd /app
python manage.py migrate --noinput
echo "Container ready. Start the API with Run and Debug → Agentradez: API + Celery"
