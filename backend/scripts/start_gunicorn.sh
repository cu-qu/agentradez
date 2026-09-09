#!/usr/bin/env bash
set -o errexit

# Collect into STATIC_ROOT in this container. Railway pre-deploy writes are
# discarded, so gunicorn would otherwise serve Django admin with no CSS.
python manage.py collectstatic --noinput

exec python -m gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:?PORT is required}" \
  --access-logfile - \
  --error-logfile -
