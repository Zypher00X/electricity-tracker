#!/usr/bin/env bash
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p tmp/security/render
cat > tmp/security/render/fixture.env <<'ENV'
APP_ENV=production
PUBLIC_ORIGIN=https://powertrack.test
COOKIE_SECURE=true
AUTH_COOKIE_NAME=__Host-powertrack_access_token
JWT_SECRET_KEY=render-fixture-only-render-fixture-only-render-fixture-only-render-fixture-only
GOOGLE_OAUTH_CLIENT_ID=fixture-only
GOOGLE_OAUTH_CLIENT_SECRET=fixture-only
GOOGLE_SPREADSHEET_ID=fixture-sheet
GOOGLE_USERS_SHEET=test_users
GOOGLE_ELECTRICITY_SHEET=test_electricity
GOOGLE_APPLIANCES_SHEET=test_appliances
GOOGLE_USAGE_SHEET=test_usage
GOOGLE_SETTINGS_SHEET=test_settings
GOOGLE_REPORTS_SHEET=test_reports
REDIS_URL=redis://powertrack_render_redis:6379/0
REDIS_ALLOW_PASSWORDLESS_PRIVATE=true
GOOGLE_CREDENTIALS_PATH=/etc/secrets/google-service-account.json
PORT=12345
WEB_CONCURRENCY=1
ENV
printf '%s' '{"fixture_only":true}' > tmp/security/render/google-service-account.json
chmod 640 tmp/security/render/google-service-account.json
docker network create powertrack_render_test >/dev/null
docker run -d --name powertrack_render_redis --network powertrack_render_test redis:7-alpine redis-server --maxmemory 128mb --maxmemory-policy noeviction --save '' --appendonly no >/dev/null
# Named volume reproduces Render's group-readable 1000 secret-file permission.
docker volume create powertrack_render_secrets >/dev/null
docker run --rm --user 0 -v powertrack_render_secrets:/secret powertrack:render sh -c 'printf "%s" "{\"fixture_only\":true}" > /secret/google-service-account.json; chown 0:1000 /secret/google-service-account.json; chmod 640 /secret/google-service-account.json'
docker run -d --name powertrack_render_app --network powertrack_render_test --env-file tmp/security/render/fixture.env -v powertrack_render_secrets:/etc/secrets:ro -p 127.0.0.1:8002:12345 --memory 512m --cpus 1 --read-only --tmpfs /tmp:mode=1777 --cap-drop ALL --security-opt no-new-privileges powertrack:render >/dev/null
for attempt in $(seq 1 30); do
 if docker exec powertrack_render_app python -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:12345/health',headers={'Host':'powertrack.test'}))" >/dev/null 2>&1; then break; fi
 sleep 1
done
docker exec powertrack_render_app python -c "import os,json;from app.core.redis import ping_redis;from app.electricity.service import feature_redis;assert ping_redis() and feature_redis.ping();assert json.load(open(os.environ['GOOGLE_CREDENTIALS_PATH']))['fixture_only'];assert os.getuid()==10001;print('runtime Redis clients, non-root and group-readable secret: passed')"
# Second runtime mounts only synthetic fixtures; no actual .env or provider key.
docker run -d --name powertrack_render_fixture --network powertrack_render_test --network-alias electricity_test_app --env-file tmp/security/render/fixture.env -e APP_ENV=development -e PUBLIC_ORIGIN=http://localhost:8003 -e COOKIE_SECURE=false -e AUTH_COOKIE_NAME=powertrack_access_token -e ELECTRICITY_TEST_MODE=synthetic -e PYTHONPATH=/app:/tests -e ADVICE_PROVIDER_RPM=60 -e ADVICE_PROVIDER_DAILY_LIMIT=1000 -v "$PWD/tests:/tests:ro" -p 127.0.0.1:8003:8000 --memory 512m --cpus 1 powertrack:render uvicorn large_data_runtime:app --host 0.0.0.0 --port 8000 --no-proxy-headers >/dev/null
