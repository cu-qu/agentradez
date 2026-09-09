#!/usr/bin/env bash
# Print live X API responses for a connected copy-trade strategy.
# Does not ingest tweets or create signals.
#
# Usage:
#   ./scripts/probe_x_client.sh
#   ./scripts/probe_x_client.sh --all
#   ./scripts/probe_x_client.sh --handle some_trader --max-results 20
#   ./scripts/probe_x_client.sh --source-id 1
#   ./scripts/probe_x_client.sh --strategy-id 1

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if docker compose exec -T app true >/dev/null 2>&1; then
  docker compose exec -T app python manage.py probe_x_client "$@"
else
  python manage.py probe_x_client "$@"
fi
