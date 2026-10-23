"""Authorized HTTP adversarial checks against dummy-only isolated runtime."""
import json
from pathlib import Path
from uuid import uuid4
import requests

BASE = 'http://localhost:8001'
checks = []
def checked(name, condition):
    if not condition: raise AssertionError(name)
    checks.append(name)
def account(index):
    session = requests.Session()
    response = session.post(BASE + '/api/auth/login', json={'identifier': f'large-fixture-{index}@example.com', 'password': 'LargeFixturePassword123!'}, timeout=20)
    checked('login fixture ' + str(index), response.status_code == 200)
    checked('HttpOnly SameSite cookie', 'HttpOnly' in response.headers['Set-Cookie'] and 'SameSite=lax' in response.headers['Set-Cookie'])
    return session

if __name__ == '__main__':
    checked('isolated target', requests.get(BASE + '/_test/large-stats', timeout=10).json()['isolated'])
    first, second = account(0), account(1)
    paths = ['/api/auth/me', '/api/dashboard', '/api/history', '/api/appliances?billing_month=2026-05', '/api/analysis', '/api/settings', '/api/advice/context?month=2026-05', '/api/advice/reports']
    for path in paths:
        checked('anonymous rejected ' + path, requests.get(BASE + path, timeout=20).status_code == 401)
        response = first.get(BASE + path, timeout=20)
        checked('authorized read ' + path, response.status_code == 200)
        checked('private no-store ' + path, response.headers.get('Cache-Control') == 'no-store')
    checked('diagnostic anonymous denied', requests.get(BASE + '/api/google-sheets/health', timeout=10).status_code == 401)
    checked('diagnostic user denied', first.get(BASE + '/api/google-sheets/health', timeout=10).status_code == 403)
    for path in ('/.env', '/frontend/../.env', '/frontend/%2e%2e/.env', '/app/credentials/google-service-account.json'):
        checked('file disclosure denied ' + path, requests.get(BASE + path, timeout=10).status_code in (400,404))
    for path in ('/api/auth/login', '/api/auth/logout', '/api/electricity', '/api/appliances', '/api/advice/chat', '/api/advice/export-prompt', '/api/advice/reports'):
        response = first.post(BASE + path, json={}, headers={'Origin': 'https://evil.example'}, timeout=10)
        checked('cross-origin mutation rejected ' + path, response.status_code == 403)
    checked('opaque origin rejected', first.post(BASE + '/api/auth/logout', headers={'Origin': 'null'}, timeout=10).status_code == 403)
    checked('oversized body rejected', first.post(BASE + '/api/advice/chat', data=b'x'*70000, timeout=10).status_code == 413)
    checked('bad month rejected', first.get(BASE + '/api/appliances', params={'billing_month':'2026-99'}, timeout=10).status_code == 422)
    checked('query injection does not broaden results', first.get(BASE + '/api/history', params={'q':"' OR 1=1 --"}, timeout=10).json()['total'] == 0)
    other = second.get(BASE + '/api/history', timeout=10).json()['records'][0]
    response = first.delete(BASE + '/api/history/' + other['record_id'], json={'expected_updated_at':other['updated_at'], 'request_id':str(uuid4())}, timeout=10)
    checked('foreign bill deletion denied', response.status_code == 404)
    response = first.get(BASE + '/api/history', params={'user_id':other['user_id']}, timeout=10).json()
    checked('owner query cannot override session', all(r['user_id'] != other['user_id'] for r in response['records']))
    original = first.get(BASE + '/api/settings', timeout=10).json()['settings']
    payload = {key: original.get(key) for key in ('residence_type','occupants','default_unit_price','default_service_charge','monthly_budget')}
    payload['expected_updated_at'] = original['updated_at']
    response = first.put(BASE + '/api/settings', json=payload, headers={'Origin':BASE}, timeout=10)
    checked('legitimate same-origin write works', response.status_code == 200)
    checked('other account settings isolated', second.get(BASE + '/api/settings', timeout=10).json()['settings']['monthly_budget'] != original['monthly_budget'])
    for _ in range(5):
        checked('export admitted', first.post(BASE + '/api/advice/export-prompt', json={'month':'2026-05'}, timeout=20).status_code == 200)
    checked('export sixth request throttled', first.post(BASE + '/api/advice/export-prompt', json={'month':'2026-05'}, timeout=20).status_code == 429)
    checked('export quota is per owner', second.post(BASE + '/api/advice/export-prompt', json={'month':'2026-05'}, timeout=20).status_code == 200)
    preflight = requests.options(BASE + '/api/settings', headers={'Origin':'https://evil.example', 'Access-Control-Request-Method':'PUT'}, timeout=10)
    checked('foreign CORS preflight not approved', 'Access-Control-Allow-Origin' not in preflight.headers)
    token = first.cookies.get('powertrack_access_token')
    parts = token.split('.'); parts[2] = ('a' if parts[2][0] != 'a' else 'b') + parts[2][1:]
    checked('forged JWT rejected', requests.get(BASE + '/api/auth/me', cookies={'powertrack_access_token':'.'.join(parts)}, timeout=10).status_code == 401)
    for index in range(6):
        response = requests.post(BASE + '/api/auth/login', json={'identifier':'large-fixture-0@example.com', 'password':'wrong-fixture-password'}, headers={'X-Forwarded-For':f'198.51.100.{index+1}'}, timeout=20)
        checked('forwarded IP cannot bypass account login throttle', response.status_code == (401 if index < 5 else 429))
    checked('other account login counter separate', requests.post(BASE + '/api/auth/login', json={'identifier':'large-fixture-1@example.com', 'password':'wrong-fixture-password'}, timeout=20).status_code == 401)
    checked('logout succeeds', first.post(BASE + '/api/auth/logout', timeout=10).status_code == 200)
    checked('logged out session denied', first.get(BASE + '/api/auth/me', timeout=10).status_code == 401)
    checked('other session still active', second.get(BASE + '/api/auth/me', timeout=10).status_code == 200)
    checked('replaying revoked cookie denied', requests.get(BASE + '/api/auth/me', cookies={'powertrack_access_token':token}, timeout=10).status_code == 401)
    Path('tmp/security/http-smoke.json').write_text(json.dumps({'synthetic_only':True, 'passed':len(checks), 'checks':checks}, indent=2), encoding='utf-8')
    print('Passed HTTP security checks:', len(checks))
