#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env.local ]; then
  cp .env.example .env.local
  echo "Created .env.local from .env.example"
fi

echo "Starting Next.js..."
docker compose up -d --build web

cat <<'EOF'

Agentradez web is up
App:  http://localhost:3000
API:  http://localhost:8001  (start the backend separately)

EOF
