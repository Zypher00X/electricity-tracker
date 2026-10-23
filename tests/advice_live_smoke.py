"""Run INSIDE an isolated live-Sheets Docker container, against its production HTTP app.
Uses only existing synthetic fixture accounts, never a production user's identity.
"""
import http.cookiejar
import json
import os
from urllib import request, error
from uuid import uuid4
from decimal import Decimal

assert os.environ['GOOGLE_USERS_SHEET'].startswith('test_')
assert os.environ['GOOGLE_SETTINGS_SHEET'].startswith('test_')
from app.services.auth_user_cache import load_users
from app.settings.repository import Repository
settings, _ = Repository().load()
assert len(settings) == 1, 'Expected exactly one fixture settings owner'
owner = settings[0][1].user_id
user = next(row for row in load_users() if row['user_id'] == owner)
assert user['email'].startswith('advice-k6-') and user['email'].endswith('@example.com')
opener = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path, data=None):
    req = request.Request('http://127.0.0.1:8000' + path,
        data=None if data is None else json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    try:
        with opener.open(req, timeout=50) as res: return res.status, json.load(res)
    except error.HTTPError as exc: return exc.code, {}


code, _ = call('/api/auth/login', {'identifier': user['email'], 'password': 'TestFixturePassword123!'})
assert code == 200, 'Fixture login failed'
code, context = call('/api/advice/context?month=2026-10')
assert code == 200 and Decimal(context['facts']['bill']['total_cost']) == 1600
before = context['quota']['remaining']
assert before >= 2, 'Fixture needs two remaining questions for smoke test'
body = {'question': 'ช่วยวิเคราะห์ภาพรวมค่าไฟและจุดที่ควรเริ่มประหยัด', 'topic': 'overview',
    'month': '2026-10', 'request_id': str(uuid4()), 'conversation_id': str(uuid4())}
code, result = call('/api/advice/chat', body)
assert code == 200, 'Actual Gemini HTTP request failed: ' + str(code)
assert result['source'] == 'gemini' and result['model'] == os.environ.get('GEMINI_MODEL', 'gemini-3.5-flash-lite')
assert result['quota']['remaining'] == before - 1 and result['context']['facts']['budget']['gap_baht'] == '200.00'
code, replay = call('/api/advice/chat', body)
assert code == 200 and replay['replayed'] and replay['quota']['remaining'] == before - 1
code, cached = call('/api/advice/chat', body | {'request_id': str(uuid4())})
assert code == 200 and cached['source'] == 'cache' and cached['usage'] == {} and cached['quota']['remaining'] == before - 2
call('/api/auth/logout', {})
print(json.dumps({'passed': True, 'path': 'HTTP -> JWT/session -> real fixture Sheets -> calculations -> real Gemini -> validated JSON -> Redis cache',
    'model': result['model'], 'source': result['source'], 'usage': result['usage'], 'idempotent_replay': True, 'second_question_cache_hit': True}))
