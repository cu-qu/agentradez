#!/usr/bin/env bash
set -euo pipefail

port_open() {
  python - <<PY
import socket
s = socket.socket()
s.settimeout(0.3)
try:
    s.connect(("127.0.0.1", int("${1}")))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
}

if [ ! -f /workspace/backend/.env ]; then
  cp /workspace/backend/.env.example /workspace/backend/.env
  echo "Created backend/.env from .env.example"
fi
if [ ! -f /workspace/web/.env.local ]; then
  cp /workspace/web/.env.example /workspace/web/.env.local
  echo "Created web/.env.local from .env.example"
fi

bash /workspace/backend/scripts/ensure_local_services.sh
su -s /bin/bash postgres -c "psql -d postgres -c \"ALTER USER postgres WITH PASSWORD 'postgres';\""

cd /workspace/backend
python manage.py migrate --noinput
python manage.py setup_base_data
if python manage.py help seed_demo >/dev/null 2>&1; then
  python manage.py seed_demo
fi

if port_open 8002; then
  echo "Runserver already listening on 8002"
else
  nohup python manage.py runserver 0.0.0.0:8002 >/tmp/agentradez-runserver.log 2>&1 &
  echo "Runserver started on 0.0.0.0:8002"
fi

cd /workspace/web
if port_open 3000; then
  echo "Next.js already listening on 3000"
else
  nohup npm run dev -- --hostname 0.0.0.0 >/tmp/agentradez-web.log 2>&1 &
  echo "Next.js started on 0.0.0.0:3000"
fi

cat <<'EOF'

agentradez is up
API:   http://localhost:8002
Docs:  http://localhost:8002/api/docs/
Admin: http://localhost:8002/admin/   (admin / change-me)
Web:   http://localhost:3000
       http://localhost:3000/how-it-works
       http://localhost:3000/strategies
       http://localhost:3000/terms

EOF
