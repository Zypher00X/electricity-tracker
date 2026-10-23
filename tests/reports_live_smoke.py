"""Execute only inside the isolated live-Sheets reports test container."""
import http.cookiejar
import json
import os
from urllib import request
from app.reports.repository import Repository
from app.reports.routes import service
from app.settings.repository import Repository as Settings
from app.services.auth_user_cache import load_users
from app.advice.context import digest

assert os.environ.get('ELECTRICITY_TEST_MODE')=='live'
assert os.environ['GOOGLE_REPORTS_SHEET'].startswith('test_')
repo=Repository();rows,_=repo.load();assert rows
owner=rows[0]['user_id'];user=next(u for u in load_users() if u['user_id']==owner)
assert user['email'].startswith('advice-k6-') and user['email'].endswith('@example.com')
opener=request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(path,data=None,method=None):
    req=request.Request('http://localhost:8000'+path,data=None if data is None else json.dumps(data).encode(),
        headers={'Content-Type':'application/json'},method=method)
    with opener.open(req,timeout=45) as r:return json.load(r)
call('/api/auth/login',{'identifier':user['email'],'password':'TestFixturePassword123!'})
id=rows[0]['report_id'];before=call('/api/advice/reports/'+id)
settings=next(r for _,r in Settings().load()[0] if r.user_id==owner)
call('/api/settings',{'residence_type':'apartment','occupants':2,'monthly_budget':'1200',
                     'expected_updated_at':settings.updated_at},'PUT')
service.cache.delete(service.cache_key)  # Force read-back from Sheets, not the report cache.
after=call('/api/advice/reports/'+id)
assert after==before
assert after['input_snapshot']['context']['facts']['budget']['monthly_budget']=='1400'
assert call('/api/advice/reports',{'report_id':id})['already_saved']
new_rows,_=repo.load();assert len(new_rows)==len(rows)
for row in new_rows:
    assert row['input_hash']==digest(json.loads(row['input_snapshot_json']))
    assert json.loads(row['analysis_json'])['answer']['in_scope']
print(json.dumps({'passed':True,'reports_read_back':len(rows),'snapshot_immutable_after_settings_edit':True,
                  'retry_no_duplicate':True,'hashes_match':True}))
