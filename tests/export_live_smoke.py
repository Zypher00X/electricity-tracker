"""Run inside the temporary live-Sheets export test container, never production."""
import http.cookiejar
import json
import os
from urllib import request
from uuid import uuid4
assert os.environ['GOOGLE_USERS_SHEET'].startswith('test_')
from app.services.auth_user_cache import load_users
from app.settings.repository import Repository
rows, _ = Repository().load(); assert len(rows) == 1
user = next(u for u in load_users() if u['user_id'] == rows[0][1].user_id)
assert user['email'].startswith('advice-k6-') and user['email'].endswith('@example.com')
opener = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path, body=None):
    req = request.Request('http://localhost:8000' + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=35) as response: return json.load(response)


assert call('/_test/advice')['provider'] == 'load-test-stub-not-gemini'
call('/api/auth/login', {'identifier': user['email'], 'password': 'TestFixturePassword123!'})
for _ in range(5):
    call('/api/advice/chat', {'question': 'ช่วยวิเคราะห์ภาพรวมค่าไฟและจุดที่ควรเริ่มประหยัด', 'topic': 'overview',
        'month': '2026-10', 'conversation_id': str(uuid4()), 'request_id': str(uuid4())})
assert call('/api/advice/context?month=2026-10')['quota']['remaining'] == 0
before = call('/_test/advice')['provider_calls']
result = call('/api/advice/export-prompt', {'month': '2026-10'})
assert 'ยอดรวมบิล: 1600 บาท' in result['prompt'] and 'งบค่าไฟ: 1400 บาท' in result['prompt']
assert call('/api/advice/context?month=2026-10')['quota']['remaining'] == 0
assert call('/_test/advice')['provider_calls'] == before
call('/api/auth/logout', {})
print(json.dumps({'passed': True, 'fixture_email': user['email'], 'chat_quota': 0, 'export_remaining': result['rate_limit']['remaining'], 'model_calls_added_by_export': 0}))
