#!/bin/bash
set -euo pipefail

case "${SITESCORE_ROLE:-api}" in
  api)
    python -m sitescore check-config
    alembic upgrade head
    exec uvicorn sitescore.api:app --host 0.0.0.0 --port 8000 \
      --workers "${WEB_CONCURRENCY:-2}" --no-server-header
    ;;
  worker)
    python -m sitescore check-config
    # Start Chromium once so the first speed test is not slowed by a cold start.
    timeout 60 "${SITESCORE_CHROME_PATH:-/usr/bin/chromium}" --headless=new --no-sandbox --disable-gpu \
      --disable-dev-shm-usage --dump-dom about:blank >/dev/null 2>&1 || true
    # A pool of workers. If one stops (a lost Redis connection, or the kernel killing it
    # when memory runs out) the pool starts a new one within a second, and the scans
    # running in the other workers carry on. The container restarts only if the pool
    # itself stops. Every worker can run the scheduler for retried report emails; RQ
    # makes sure only one does at a time.
    exec rq worker-pool sitescore --num-workers "${WORKER_COUNT:-4}" --url "$SITESCORE_REDIS_URL"
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  cleanup)
    exec python -m sitescore cleanup
    ;;
  *)
    exec "$@"
    ;;
esac
