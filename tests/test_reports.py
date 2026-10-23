import copy
import json
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from conftest import login
from test_appliances import appliances
from test_advice import advice, payload
from app.reports import routes
from app.reports.service import Service
from app.advice.context import digest


class MemoryReports:
    def __init__(self): self.records=[]; self.loads=0; self.writes=0; self.fail_after=False
    def load(self): self.loads+=1; return copy.deepcopy(self.records), len(self.records)+1
    def insert(self, record, row, guard):
        guard(); self.records.append(copy.deepcopy(record)); self.writes+=1
        if self.fail_after: self.fail_after=False; raise TimeoutError('ambiguous commit')


@pytest.fixture
def reports(advice):
    client, ai, provider, cache, *_ = advice
    repo=MemoryReports(); service=Service(repo,cache,'test:reports')
    client.app.include_router(routes.router)
    client.app.dependency_overrides[routes.get_service]=lambda:service
    return client,ai,provider,repo,service


def generate(client):
    response=client.post('/api/advice/chat',json=payload()); assert response.status_code==200,response.text
    return response.json()


def save(client,id): return client.post('/api/advice/reports',json={'report_id':id})


def test_server_snapshot_persistence_and_history(reports):
    client,ai,provider,repo,service=reports
    result=generate(client); id=result['report_candidate_id']
    assert repo.writes==0
    stored=save(client,id); assert stored.status_code==200,stored.text
    assert not stored.json()['already_saved'] and repo.writes==1
    row=repo.records[0]
    assert row['user_id']=='user-a' and row['billing_month']=='2026-10'
    inputs=json.loads(row['input_snapshot_json']); analysis=json.loads(row['analysis_json'])
    assert inputs['context']==result['context'] and analysis['answer']==result['answer']
    assert inputs['question']==payload()['question'] and row['input_hash']==digest(inputs)
    assert row['provider']=='gemini' and row['model']==provider.model and row['created_at']
    assert len(provider.calls)==1
    detail=client.get('/api/advice/reports/'+id).json()
    assert detail['input_snapshot']==inputs and detail['analysis']==analysis
    assert client.get('/api/advice/reports?month=2026-09').json()['total']==0
    listed=client.get('/api/advice/reports?page_size=1').json()
    assert listed['total']==1 and listed['items'][0]['report_id']==id
    assert client.get('/api/advice/reports').headers['cache-control']=='no-store'


def test_duplicate_cached_answer_and_reload(reports):
    client,ai,provider,repo,service=reports
    first=generate(client); second=generate(client)
    assert second['source']=='cache' and second['report_candidate_id']==first['report_candidate_id']
    id=first['report_candidate_id']; save(client,id)
    calls=repo.loads
    for _ in range(8): assert save(client,id).json()['already_saved']
    assert repo.writes==1 and repo.loads==calls and len(provider.calls)==1
    ai.cache.delete(service.cache_key)
    assert save(client,id).json()['already_saved'] and repo.writes==1


def test_owner_isolation_and_tampering(reports):
    client,ai,provider,repo,service=reports
    id=generate(client)['report_candidate_id'];save(client,id)
    login(client,'user-b')
    assert client.get('/api/advice/reports').json()['total']==0
    assert client.get('/api/advice/reports/'+id).status_code==404
    assert save(client,id).status_code==404
    assert save(client,str(uuid4())).status_code==404
    assert client.post('/api/advice/reports',json={'report_id':id,'answer':'forged'}).status_code==422
    assert repo.writes==1


def test_snapshot_remains_frozen_after_source_change(reports):
    client,ai,provider,repo,service=reports
    id=generate(client)['report_candidate_id'];save(client,id)
    old=client.get('/api/advice/reports/'+id).json()
    client.post('/api/electricity',json={'billing_month':'2026-09','previous_meter':0,'current_meter':999,'unit_price':'8','service_charge':'0'})
    assert client.get('/api/advice/reports/'+id).json()==old
    assert generate(client)['report_candidate_id']!=id


def test_local_answers_not_saveable_and_quota_independent(reports):
    client,ai,provider,repo,service=reports
    first=generate(client)
    for data in [payload(topic='custom',question='เขียนนิยายเกี่ยวกับแมว'),payload(month='2026-01')]:
        r=client.post('/api/advice/chat',json=data).json();assert r['report_candidate_id'] is None
    for _ in range(2):generate(client)
    assert ai.quota('user-a')['remaining']==0
    assert save(client,first['report_candidate_id']).status_code==200
    assert ai.quota('user-a')['remaining']==0
    assert repo.writes==1


def test_ambiguous_write_retry_does_not_duplicate(reports):
    client,ai,provider,repo,service=reports
    id=generate(client)['report_candidate_id'];repo.fail_after=True
    assert save(client,id).status_code==503
    assert save(client,id).json()['already_saved'] and repo.writes==1


def test_concurrent_saves_one_row(reports):
    client,ai,provider,repo,service=reports
    id=generate(client)['report_candidate_id']
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:service.save('user-a',id,ai),range(12)))
    assert repo.writes==1 and sum(not r['already_saved'] for r in results)==1


def test_expired_candidate_and_invalid_requests(reports):
    client,ai,provider,repo,service=reports
    id=generate(client)['report_candidate_id'];ai.cache.delete(ai.owner_key('user-a')+':report-candidate:'+id)
    assert save(client,id).status_code==404
    assert save(client,'invalid').status_code==422
    assert client.get('/api/advice/reports?page=0').status_code==422
    assert client.post('/api/advice/reports',json={'report_id':id},headers={'Origin':'https://evil.example'}).status_code==403
    client.cookies.clear()
    assert client.get('/api/advice/reports').status_code==401


def test_sheets_cell_size_guard(reports):
    client,ai,provider,repo,service=reports
    id=generate(client)['report_candidate_id'];key=ai.owner_key('user-a')+':report-candidate:'+id
    row=json.loads(ai.cache.get(key));row['input_snapshot_json']='😀'*25001;ai.cache.set(key,json.dumps(row))
    assert save(client,id).status_code==422 and repo.writes==0


def test_cold_history_reads_coalesce_and_paginate(reports):
    client,ai,provider,repo,service=reports
    id=generate(client)['report_candidate_id'];save(client,id)
    row=copy.deepcopy(repo.records[0])
    for index in range(8):repo.records.append(row|{'report_id':str(uuid4()),'billing_month':'2026-09'})
    ai.cache.delete(service.cache_key);before=repo.loads
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:service.list('user-a','2026-09',2,5),range(16)))
    assert repo.loads==before+1
    assert all(r['total']==8 and len(r['items'])==3 for r in results)


def test_sheets_429_cooldown_avoids_repeat_io(reports,monkeypatch):
    from gspread.exceptions import APIError
    import httpx
    client,ai,provider,repo,service=reports
    calls=[]
    def fail():
        calls.append(1)
        raise APIError(httpx.Response(429,json={'error':{'code':429,'message':'quota','status':'RESOURCE_EXHAUSTED'}}))
    monkeypatch.setattr(repo,'load',fail)
    for _ in range(4):
        r=client.get('/api/advice/reports');assert r.status_code==503 and r.headers['retry-after']=='10'
    assert len(calls)==1
