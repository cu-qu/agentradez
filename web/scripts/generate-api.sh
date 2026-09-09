#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

candidates=()
if [ -n "${API_SCHEMA_URL:-}" ]; then
  candidates+=("$API_SCHEMA_URL")
fi
candidates+=(
  "http://localhost:8001/api/schema/"
  "http://host.docker.internal:8001/api/schema/"
)

url=""
for candidate in "${candidates[@]}"; do
  if curl -sf --connect-timeout 2 -o /dev/null "$candidate"; then
    url="$candidate"
    break
  fi
done

if [ -z "$url" ]; then
  echo "Could not reach the OpenAPI schema. Is the API running on localhost:8001?" >&2
  exit 1
fi

echo "Fetching $url"
curl -sS "$url" -o openapi.json
npx openapi-typescript openapi.json -o src/lib/api/schema.ts
echo "Wrote src/lib/api/schema.ts"
