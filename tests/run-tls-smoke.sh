#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/electricity_tracker
mkdir -p tmp/security/tls
openssl req -x509 -newkey rsa:2048 -nodes -keyout tmp/security/tls/server.key -out tmp/security/tls/server.crt -days 2 -subj /CN=localhost -addext subjectAltName=DNS:localhost >/dev/null 2>&1
docker run -d --name powertrack_tls_app --network powertrack_security_test --network-alias electricity_test_app \
   --read-only --tmpfs /tmp:size=32m,mode=1777 --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 1g --cpus 2 \
  -e REDIS_HOST=powertrack_security_redis -e REDIS_PASSWORD=isolated-security-test \
  -e JWT_SECRET_KEY=isolated-security-fixture-only-isolated-security-fixture-only-isolated-security-fixture-only \
  -e GOOGLE_OAUTH_CLIENT_ID=fixture-client -e GOOGLE_OAUTH_CLIENT_SECRET=fixture-only \
  -e GOOGLE_SPREADSHEET_ID=test-only-security-sheet -e GOOGLE_USERS_SHEET=test_users \
  -e GOOGLE_ELECTRICITY_SHEET=test_electricity -e GOOGLE_SETTINGS_SHEET=test_settings \
  -e GOOGLE_APPLIANCES_SHEET=test_appliances -e GOOGLE_USAGE_SHEET=test_usage \
  -e GOOGLE_REPORTS_SHEET=test_reports \
  -e ELECTRICITY_TEST_MODE=synthetic -e COOKIE_SECURE=true -e APP_ENV=production -e PUBLIC_ORIGIN=https://localhost:8443 -e AUTH_COOKIE_NAME=__Host-powertrack_access_token -e PYTHONPATH=/app:/tests \
  -e ADVICE_PROVIDER_RPM=60 -e ADVICE_PROVIDER_DAILY_LIMIT=1000 \
  -v /mnt/c/electricity_tracker/tests:/tests:ro \
  powertrack:security-reviewed uvicorn large_data_runtime:app --host 0.0.0.0 --port 8000 --no-server-header --no-proxy-headers >/dev/null

cat > tmp/security/tls/nginx.conf <<'CONF'
events {}
http {
 server {
  listen 443 ssl;
  server_name localhost;
  ssl_certificate /tls/server.crt;
  ssl_certificate_key /tls/server.key;
  ssl_protocols TLSv1.2 TLSv1.3;
  location / {
   proxy_pass http://powertrack_tls_app:8000;
   proxy_set_header Host $http_host;
   proxy_set_header X-Forwarded-Proto https;
   proxy_set_header X-Forwarded-For $remote_addr;
  }
 }
}
CONF
docker run -d --name powertrack_tls_proxy --network powertrack_security_test -p 127.0.0.1:8443:443 -v /mnt/c/electricity_tracker/tmp/security/tls:/tls:ro -v /mnt/c/electricity_tracker/tmp/security/tls/nginx.conf:/etc/nginx/nginx.conf:ro nginx:stable-alpine >/dev/null
