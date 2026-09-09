#!/usr/bin/env bash
set -euo pipefail
cd /app
if [ ! -f .env.local ]; then
  cp .env.example .env.local
fi
if [ ! -d node_modules/next ]; then
  npm ci
fi
exec "$@"
