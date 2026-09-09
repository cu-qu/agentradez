#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

python manage.py migrate --noinput
python manage.py setup_base_data
if python manage.py help seed_demo >/dev/null 2>&1; then
  python manage.py seed_demo
fi

if ! python - <<'PY'
import socket
s = socket.socket()
s.settimeout(0.3)
try:
    s.connect(("127.0.0.1", 8000))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
then
  nohup python manage.py runserver 0.0.0.0:8000 >/tmp/agentradez-runserver.log 2>&1 &
  echo "Runserver started on 0.0.0.0:8000"
else
  echo "Runserver already listening on 8000"
fi
