"""Network TLS and secure session checks; synthetic data only, certificate verified."""
import json
from pathlib import Path
import requests
base = 'https://localhost:8443'
s = requests.Session()
s.verify = 'tmp/security/tls/server.crt'
checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)
r = s.get(base + '/health', timeout=15)
check('TLS certificate and hostname verified', r.status_code == 200)
check('production HSTS', r.headers.get('Strict-Transport-Security') == 'max-age=31536000')
check('seed isolated fixture', s.post(base + '/_test/large-seed', timeout=30).status_code == 200)
r = s.post(base + '/api/auth/login', json={'identifier':'large-fixture-2@example.com','password':'LargeFixturePassword123!'}, headers={'Origin':base}, timeout=20)
check('HTTPS login', r.status_code == 200)
cookie = r.headers.get('Set-Cookie', '')
check('host prefix and Secure HttpOnly SameSite', cookie.startswith('__Host-powertrack_access_token=') and all(v in cookie for v in ('Secure','HttpOnly','SameSite=lax','Path=/')) and 'Domain=' not in cookie)
check('authenticated HTTPS request', s.get(base + '/api/dashboard', timeout=20).status_code == 200)
prepared = s.prepare_request(requests.Request('GET', 'http://localhost:8000/api/dashboard'))
check('secure cookie absent over HTTP', 'Cookie' not in prepared.headers)
check('cross-origin logout rejected', s.post(base + '/api/auth/logout', headers={'Origin':'https://evil.example'}, timeout=10).status_code == 403)
check('production docs disabled', s.get(base + '/docs', timeout=10).status_code == 404)
try:
    s.get('https://127.0.0.1:8443/health', timeout=10)
except requests.exceptions.SSLError:
    check('invalid certificate hostname rejected', True)
else:
    raise AssertionError('hostname validation missing')
Path('tmp/security/tls-smoke.json').write_text(json.dumps({'passed':True,'checks':checks,'synthetic_only':True,'real_deployment_tls_configured':False}, indent=2))
print(json.dumps({'passed':True,'checks':len(checks)}))
