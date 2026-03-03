#!/bin/bash
set -euo pipefail

log_error() {
  local exit_code=$?
  local line_no=${BASH_LINENO[0]:-unknown}
  local cmd=${BASH_COMMAND:-unknown}
  echo "[start][error] Command failed at line ${line_no}: ${cmd}" >&2
  echo "[start][error] Exit code: ${exit_code}" >&2
}

trap log_error ERR

cd /app

# -----------------------------
# Wait for Postgres (DNS + TCP)
# -----------------------------
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}
MAX_WAIT_SEC=${DB_WAIT_TIMEOUT_SEC:-60}

echo "[start] Waiting for DB DNS (${DB_HOST})..."
dns_ready=0
for ((i=1; i<=MAX_WAIT_SEC; i++)); do
  if getent hosts "${DB_HOST}" >/dev/null 2>&1; then
    dns_ready=1
    break
  fi
  sleep 1
done

if [ "${dns_ready}" -ne 1 ]; then
  echo "[start][error] DB DNS lookup timed out after ${MAX_WAIT_SEC}s (${DB_HOST})." >&2
  exit 1
fi

echo "[start] Waiting for DB TCP (${DB_HOST}:${DB_PORT})..."
tcp_ready=0
for ((i=1; i<=MAX_WAIT_SEC; i++)); do
  if (echo >"/dev/tcp/${DB_HOST}/${DB_PORT}") >/dev/null 2>&1; then
    tcp_ready=1
    break
  fi
  sleep 1
done

if [ "${tcp_ready}" -ne 1 ]; then
  echo "[start][error] DB TCP connectivity timed out after ${MAX_WAIT_SEC}s (${DB_HOST}:${DB_PORT})." >&2
  exit 1
fi

# DB migration (safe to run repeatedly)
# Use a single canonical head to avoid revision drift from stale multi-head stamps.
echo "[start] Running Alembic migrations..."
ALEMBIC_TIMEOUT_SEC=${ALEMBIC_TIMEOUT_SEC:-180}
if ! timeout "${ALEMBIC_TIMEOUT_SEC}" alembic upgrade head; then
  echo "[start][error] Alembic migration failed." >&2
  exit 1
fi
echo "[start] Alembic migrations completed."

echo "[start] Seeding demo accounts..."
if ! PYTHONPATH=/app python /app/scripts/seed_demo_accounts.py; then
  echo "[start][error] Seed demo accounts failed." >&2
  exit 1
fi

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
