#!/bin/bash
set -euo pipefail

cd /app

# -----------------------------
# Wait for Postgres (DNS + TCP)
# -----------------------------
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}
MAX_WAIT_SEC=${DB_WAIT_TIMEOUT_SEC:-60}

echo "[start] Waiting for DB DNS (${DB_HOST})..."
for ((i=1; i<=MAX_WAIT_SEC; i++)); do
  if getent hosts "${DB_HOST}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "[start] Waiting for DB TCP (${DB_HOST}:${DB_PORT})..."
for ((i=1; i<=MAX_WAIT_SEC; i++)); do
  if (echo >"/dev/tcp/${DB_HOST}/${DB_PORT}") >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# DB migration (safe to run repeatedly)
alembic upgrade heads

echo "[start] Seeding demo accounts..."
PYTHONPATH=/app python /app/scripts/seed_demo_accounts.py

mkdir -p static/fonts
if [ ! -f static/fonts/NotoSans-Regular.ttf ]; then
  echo "[start] Downloading NotoSans-Regular.ttf..."
  wget -q -O static/fonts/NotoSans-Regular.ttf https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf || true
fi

if [ "${RELOAD:-0}" = "1" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
