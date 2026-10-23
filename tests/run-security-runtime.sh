#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/electricity_tracker
docker network create powertrack_security_test >/dev/null
docker run -d --name powertrack_security_redis --network powertrack_security_test \
  --user 999:1000 --read-only --tmpfs /data:size=64m,mode=1777 --cap-drop ALL --security-opt no-new-privileges \
  redis:7-alpine redis-server --save '' --appendonly no --requirepass isolated-security-test \
  --maxmemory 256mb --maxmemory-policy noeviction >/dev/null
docker run -d --name powertrack_security_app --network powertrack_security_test --network-alias electricity_test_app \
  -p 127.0.0.1:8001:8000 --read-only --tmpfs /tmp:size=32m,mode=1777 --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 1g --cpus 2 \
  -e REDIS_HOST=powertrack_security_redis -e REDIS_PASSWORD=isolated-security-test \
  -e JWT_SECRET_KEY=isolated-security-fixture-only-isolated-security-fixture-only-isolated-security-fixture-only \
  -e GOOGLE_OAUTH_CLIENT_ID=fixture-client -e GOOGLE_OAUTH_CLIENT_SECRET=fixture-only \
  -e GOOGLE_SPREADSHEET_ID=test-only-security-sheet -e GOOGLE_USERS_SHEET=test_users \
  -e GOOGLE_ELECTRICITY_SHEET=test_electricity -e GOOGLE_SETTINGS_SHEET=test_settings \
  -e GOOGLE_APPLIANCES_SHEET=test_appliances -e GOOGLE_USAGE_SHEET=test_usage \
  -e GOOGLE_REPORTS_SHEET=test_reports \
  -e ELECTRICITY_TEST_MODE=synthetic -e COOKIE_SECURE=false -e PYTHONPATH=/app:/tests \
  -e ADVICE_PROVIDER_RPM=60 -e ADVICE_PROVIDER_DAILY_LIMIT=1000 \
  -v /mnt/c/electricity_tracker/tests:/tests:ro \
  powertrack:security-reviewed uvicorn large_data_runtime:app --host 0.0.0.0 --port 8000 --no-server-header --no-proxy-headers >/dev/null
for attempt in $(seq 1 30); do
  if docker exec powertrack_security_app python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1; then
    echo 'Isolated security runtime ready on localhost:8001 (dummy credentials only)'
    exit 0
  fi
  sleep 1
done
docker logs powertrack_security_app
exit 1
