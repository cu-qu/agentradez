#!/usr/bin/env bash
set -euo pipefail
cd /app
if [ ! -f .env.local ]; then
  cp .env.example .env.local
fi
npm ci
