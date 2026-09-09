#!/usr/bin/env bash
set -euo pipefail
cd /app
if [ ! -f .env ]; then
  cp .env.example .env
fi
pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py setup_base_data
