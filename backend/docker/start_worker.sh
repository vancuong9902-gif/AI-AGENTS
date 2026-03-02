#!/usr/bin/env bash
set -euo pipefail

REDIS_URL=${REDIS_URL:-redis://redis:6379/0}

echo "[worker] Starting RQ worker (queues: default,index,monitor) using ${REDIS_URL}"
exec rq worker -u "${REDIS_URL}" default index monitor
