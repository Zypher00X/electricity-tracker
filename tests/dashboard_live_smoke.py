"""Read-only dashboard verification against dedicated live fixture tabs."""
import http.cookiejar
import json
import os
from decimal import Decimal
from urllib import request
from app.electricity.service import service
from app.services.auth_user_cache import load_users

assert os.environ.get('ELECTRICITY_TEST_MODE')=='live'
assert service.repository.sheet_name=='test_electricity_20261023'
assert os.environ['GOOGLE_USERS_SHEET']=='test_users_20261023'
records,_=service.repository.load();assert len(records)==3
owner=records[0].user_id;users=load_users();assert len(users)==2
for user in users:assert user['email'].startswith('dashboard-k6-') and user['email'].endswith('@example.com')
results=[]
for user in users:
    opener=request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(path,data=None):
        req=request.Request('http://localhost:8000'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with opener.open(req,timeout=45) as r:return json.load(r)
    call('/api/auth/login',{'identifier':user['email'],'password':'TestFixturePassword123!'})
    service.cache.delete(service.cache_key)  # Shared source must be refilled from actual Sheets.
    data=call('/api/dashboard?month=2026-10')
    own=[r for r in records if r.user_id==user['user_id']]
    if own:
        assert user['user_id']==owner
        selected=next(r for r in own if r.billing_month=='2026-10')
        assert Decimal(data['total_cost'])==selected.total_cost==300
        assert data['units_used']==selected.units_used
        assert Decimal(data['average_cost'])==sum((r.total_cost for r in own),Decimal(0))/len(own)==200
        assert data['average_bill_count']==3 and Decimal(data['cost_change_percent'])==50
        assert data['available_months']==sorted((r.billing_month for r in own),reverse=True)
        assert data['series'][1]['total_cost'] is None  # June is missing, not zero.
    else:
        assert not data['has_bill'] and data['total_cost'] is None and data['available_months']==[]
        assert data['average_cost'] is None and data['cost_breakdown']==[]
    results.append({'has_bill':data['has_bill'],'average_bill_count':data['average_bill_count']})
print(json.dumps({'passed':True,'path':'real Sheets -> shared Redis cold fill -> authenticated dashboard API','accounts':results}))
