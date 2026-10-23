"""Real Sheets write/read-back using only dedicated disposable test tabs."""
import http.cookiejar
import json
import os
from decimal import Decimal
from urllib import request, error
from uuid import uuid4
from app.electricity.repository import SheetRepository
from app.electricity.service import service as storage
from app.services.auth_user_cache import load_users
from app.settings.repository import Repository as Settings
from app.reports.repository import Repository as Reports

assert os.environ.get('ELECTRICITY_TEST_MODE')=='live'
assert os.environ['GOOGLE_ELECTRICITY_SHEET'].startswith('test_')
assert os.environ['GOOGLE_USERS_SHEET'].startswith('test_')
owner=Settings().load()[0][0][1].user_id
users=load_users();a=next(u for u in users if u['user_id']==owner);b=next(u for u in users if u['user_id']!=owner)
for u in (a,b):assert u['email'].startswith('advice-k6-') and u['email'].endswith('@example.com')
def session(user):
    opener=request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(path,data=None,method=None,expected=200):
        req=request.Request('http://localhost:8000'+path,data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type':'application/json'},method=method)
        try:
            with opener.open(req,timeout=45) as r:
                assert r.status==expected,(path,r.status);return json.load(r)
        except error.HTTPError as exc:
            assert exc.code==expected,(path,exc.code);return json.load(exc)
    call('/api/auth/login',{'identifier':user['email'],'password':'TestFixturePassword123!'})
    return call
ca,cb=session(a),session(b)
repo=SheetRepository();initial,_,_=repo.load_indexed();original=next(r for r in initial if r.user_id==owner)
assert original.units_used==100 and original.total_cost==Decimal('850'), 'Run browser edit first'
spare=ca('/api/electricity',{'billing_month':'2026-11','previous_meter':0,'current_meter':50,'unit_price':'8','service_charge':'0'},'POST',201)['record']
other=cb('/api/electricity',{'billing_month':'2026-12','previous_meter':0,'current_meter':10,'unit_price':'4','service_charge':'0'},'POST',201)['record']
rows,positions,_=repo.load_indexed();spare_index=positions[spare['record_id']];other_index=positions[other['record_id']]
assert other_index>spare_index
deletion={'expected_updated_at':spare['updated_at'],'request_id':str(uuid4())}
ca('/api/history/'+spare['record_id'],deletion,'DELETE')
rows,positions,_=repo.load_indexed()
assert spare['record_id'] not in positions and positions[other['record_id']]==other_index
escaped=repo.sheet_name.replace("'","''")
cleared=repo.connection().values_get(repo.spreadsheet_id,f"'{escaped}'!A{spare_index+1}:L{spare_index+1}").get('values',[])
assert not cleared or not any(any(row) for row in cleared)
before=ca('/api/advice/context?month=2026-10')
edit={k:other[k] for k in ('billing_month','previous_meter','current_meter','unit_price','service_charge')}
edit.update(current_meter=80,service_charge='5',expected_updated_at=other['updated_at'],request_id=str(uuid4()))
ca('/api/history/'+other['record_id'],edit,'PUT',404)
changed=cb('/api/history/'+other['record_id'],edit,'PUT')['record']
assert Decimal(changed['total_cost'])==325 and changed['units_used']==80
rows,positions,_=repo.load_indexed();updated=next(r for r in rows if r.record_id==other['record_id'])
assert updated.total_cost==325 and positions[other['record_id']]==other_index
assert next(r for r in rows if r.record_id==original.record_id)==original
assert ca('/api/advice/context?month=2026-10')['version']==before['version'], 'Other owner changed this owner context version'
storage.cache.delete(storage.cache_key)  # Force cross-page cache refill from real Sheets.
assert ca('/api/history')['records'][0]['total_cost']=='850'
assert cb('/api/history')['records'][0]['total_cost']=='325'
assert ca('/api/analysis?end_month=2026-10')['latest']['total_cost']=='850'
assert cb('/api/advice/context?month=2026-12')['facts']['bill']['total_cost']=='325'
saved_reports,_=Reports().load()
assert all(Decimal(json.loads(r['input_snapshot_json'])['context']['facts']['bill']['total_cost'])==1600 for r in saved_reports)
# Delete the last remaining B bill and verify empty-state data without touching A.
cb('/api/history/'+other['record_id'],{'expected_updated_at':changed['updated_at'],'request_id':str(uuid4())},'DELETE')
storage.cache.delete(storage.cache_key)
assert cb('/api/history')['total']==0 and ca('/api/history')['total']==1
assert ca('/api/history/'+spare['record_id'],deletion,'DELETE')['replayed']
print(json.dumps({'passed':True,'browser_edit_read_back':850,'other_owner_update_read_back':325,
    'middle_row_cleared_without_shifting_other_owner':True,'cold_cache_reloads_correctly':True,
    'account_isolation':True,'saved_report_snapshot_unchanged':True,'last_bill_delete_empty_history':True}))
