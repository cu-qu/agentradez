#!/usr/bin/env bash
# Start local Postgres/Redis when this environment provides them
# (native packages or Docker Compose db/redis). No-op if they are already up.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

port_open() {
  python - "$1" <<'PY'
import socket, sys
s = socket.socket()
s.settimeout(0.3)
try:
    s.connect(("127.0.0.1", int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
}

if command -v pg_ctlcluster >/dev/null && [ -d /usr/lib/postgresql ]; then
  if ! port_open 5432; then
    PG_VERSION="$(ls /usr/lib/postgresql | tail -n 1)"
    pg_ctlcluster "$PG_VERSION" main start
    echo "Postgres started"
  fi
  for _ in $(seq 1 30); do
    if su -s /bin/bash postgres -c "pg_isready -q"; then
      break
    fi
    sleep 1
  done
  if ! su -s /bin/bash postgres -c "psql -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='agentradez'\"" | grep -q 1; then
    su -s /bin/bash postgres -c "createdb -O postgres agentradez"
  fi
fi

if command -v redis-server >/dev/null && ! port_open 6379; then
  redis-server --daemonize yes --bind 127.0.0.1 --port 6379
  echo "Redis started"
fi

postgres_up() { port_open 5432 || port_open 5433; }
redis_up() { port_open 6379 || port_open 6380; }

if { ! postgres_up || ! redis_up; } && [ -f "$ROOT/docker-compose.yml" ] && command -v docker >/dev/null; then
  echo "Starting Postgres and Redis via Docker Compose..."
  (cd "$ROOT" && docker compose up -d db redis)
  for _ in $(seq 1 60); do
    if postgres_up && redis_up; then
      break
    fi
    sleep 1
  done
fi
