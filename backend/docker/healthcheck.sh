#!/bin/bash
# API: answers on /api/health. Worker: can reach Redis.
if [ "${SITESCORE_ROLE:-api}" = "worker" ]; then
  exec python -c "import os, redis; redis.Redis.from_url(os.environ['SITESCORE_REDIS_URL']).ping()"
fi
exec curl -fsS http://127.0.0.1:8000/api/health >/dev/null
