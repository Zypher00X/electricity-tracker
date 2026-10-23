"""Production flags and cookie attributes, with all external auth I/O stubbed."""
import os
import sys
import json
sys.path.insert(0, '/app')
for key, value in {'APP_ENV':'production', 'PUBLIC_ORIGIN':'https://powertrack.test', 'COOKIE_SECURE':'true',
                   'JWT_SECRET_KEY':'production-config-fixture-'*5, 'REDIS_PASSWORD':'fixture-only',
                   'GOOGLE_OAUTH_CLIENT_ID':'fixture-client','GOOGLE_OAUTH_CLIENT_SECRET':'fixture-only'}.items():
    os.environ[key] = value
from fastapi.testclient import TestClient
from app.main import app
from app.routes import auth
user = dict(user_id='fixture', full_name='Fixture', email='fixture@example.com', phone='0899999999', role='user', status='active')
auth.find_user_by_identifier = lambda _: user
auth.consume_login_ip_limit = lambda _: None
auth.consume_login_failure_limit = lambda *a: None
auth.reset_login_failure_limit = lambda *a: None
auth.login_user = lambda **kw: {'access_token':'fixture-token', 'message':'ok', 'user':user}
client = TestClient(app, base_url='https://powertrack.test')
response = client.get('/health')
assert response.status_code == 200 and response.headers['strict-transport-security'] == 'max-age=31536000'
assert client.get('/health', headers={'Host':'evil.example'}).status_code == 400
for path in ('/docs','/redoc','/openapi.json'): assert client.get(path).status_code == 404
response = client.post('/api/auth/login', json={'identifier':'fixture@example.com','password':'fixture'}, headers={'Origin':'https://powertrack.test'})
assert response.status_code == 200
assert all(flag in response.headers['set-cookie'] for flag in ('Secure','HttpOnly','SameSite=lax'))
assert client.post('/api/auth/logout', headers={'Origin':'https://evil.example'}).status_code == 403
print(json.dumps({'passed':True, 'external_auth_io_stubbed':True, 'secure_cookie':True, 'host_guard':True, 'hsts':True, 'public_docs_disabled':True}))
