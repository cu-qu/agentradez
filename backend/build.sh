#!/usr/bin/env bash
set -o errexit

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files (WhiteNoise)..."
python manage.py collectstatic --noinput

echo "Seeding base data..."
python manage.py setup_base_data

echo "Build complete."
