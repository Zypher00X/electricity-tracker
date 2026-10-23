#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/electricity_tracker
mode="${1:-synthetic}"
action="${2:-run}"
if [[ "$mode" != synthetic && "$mode" != live ]]; then exit 2; fi
if [[ "$action" != run && "$action" != serve ]]; then exit 2; fi
mkdir -p tmp/k6
network="powertrack_advice_test_${mode}"
redis_name="powertrack_advice_test_redis_${mode}"
app_name="powertrack_advice_test_app_${mode}"
cleanup() {
  docker logs "$app_name" > "tmp/k6/advice-${mode}-server.log" 2>&1 || true
  docker rm -f "$app_name" "$redis_name" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker network create "$network" >/dev/null
docker run -d --name "$redis_name" --network "$network" redis:7-alpine \
  redis-server --requirepass isolated-test-only >/dev/null
docker run -d --name "$app_name" --network "$network" --network-alias electricity_test_app \
  -p 127.0.0.1:8001:8000 --env-file .env \
  -e REDIS_HOST="$redis_name" -e REDIS_PASSWORD=isolated-test-only \
  -e GOOGLE_SETTINGS_SHEET=test_settings_20261022 -e GOOGLE_APPLIANCES_SHEET=test_appliances_20261022 -e GOOGLE_USAGE_SHEET=test_usage_20261022 -e GOOGLE_USERS_SHEET=test_users_20261022 -e GOOGLE_ELECTRICITY_SHEET=test_electricity_20261022 \
  -e ELECTRICITY_TEST_MODE="$mode" -e COOKIE_SECURE=false \
  -e PYTHONPATH=/app:/tests \
  -v /mnt/c/electricity_tracker/Back__end:/app:ro \
  -v /mnt/c/electricity_tracker/Front__end:/frontend:ro \
  -v /mnt/c/electricity_tracker/tests:/tests:ro \
  electricity_tracker-backend:latest uvicorn advice_runtime:app --host 0.0.0.0 --port 8000 >/dev/null
ready=0
for attempt in $(seq 1 30); do
  if docker exec "$app_name" python -c 'import urllib.request; urllib.request.urlopen("http://localhost:8000/health")' >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then docker logs "$app_name"; exit 1; fi
if [[ "$action" == serve ]]; then
  trap - EXIT
  echo "Isolated test server ready at http://127.0.0.1:8001 (mode: $mode)"
  exit 0
fi
docker run --rm --network "$network" -e TEST_MODE="$mode" \
  -v /mnt/c/electricity_tracker/tests/k6:/scripts:ro \
  -v /mnt/c/electricity_tracker/tmp/k6:/results \
  grafana/k6:latest run --summary-export="/results/advice-${mode}.json" /scripts/advice.js
