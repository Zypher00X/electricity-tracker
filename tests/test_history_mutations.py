import copy
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import HTTPException
from conftest import login
from test_history import save
from test_appliances import appliances
from test_advice import advice, payload
from app.history.mutations import mutate, EditInput, Identity


def body(record, **changes):
    return {k:record[k] for k in ('billing_month','previous_meter','current_meter','unit_price','service_charge')} | {
        'expected_updated_at':record['updated_at'], 'request_id':str(uuid4())} | changes


def edit(client, record, **changes):
    return client.put('/api/history/'+record['record_id'], json=body(record,**changes))


def delete(client, record, **changes):
    return client.request('DELETE','/api/history/'+record['record_id'],json={
        'expected_updated_at':record['updated_at'],'request_id':str(uuid4())}|changes)


def test_edit_calculates_preserves_identity_updates_shared_cache(system):
    client,storage,repo,cache,_=system;login(client)
    september=save(client,'2026-09',100);october=save(client,'2026-10',200)
    loads=repo.loads
    result=edit(client,september,current_meter=125,unit_price='8',service_charge='50')
    assert result.status_code==200,result.text
    row=result.json()['record']
    assert row['record_id']==september['record_id'] and row['created_at']==september['created_at']
    assert row['updated_at']!=september['updated_at']
    assert row['units_used']==125 and Decimal(row['energy_cost'])==1000 and Decimal(row['total_cost'])==1050
    history=client.get('/api/history').json()['records']
    assert Decimal(history[0]['change_percent'])==Decimal('-81.0')
    assert Decimal(history[1]['total_cost'])==1050
    assert Decimal(storage.cached()[0].total_cost)==200  # Oct remains unchanged.
    assert repo.loads==loads+1
    assert client.get('/api/electricity').json()['records'][1]['record_id']==row['record_id']
    assert result.headers['cache-control']=='no-store'


def test_delete_recalculates_next_month_and_allows_recreate(system):
    client,storage,repo,cache,_=system;login(client)
    previous=save(client,'2026-09');current=save(client,'2026-10',200)
    assert delete(client,previous).status_code==200
    rows=client.get('/api/history').json()['records']
    assert len(rows)==1 and rows[0]['change_percent'] is None
    assert all(r.record_id!=previous['record_id'] for r in storage.cached())
    recreated=save(client,'2026-09',50)
    assert recreated['record_id']!=previous['record_id']
    assert Decimal(client.get('/api/history').json()['records'][0]['change_percent'])==300


def test_owner_isolation_before_source_io(system):
    client,storage,repo,*_=system;login(client)
    record=save(client,'2026-10');login(client,'user-b');loads=repo.loads
    assert edit(client,record,current_meter=999).status_code==404
    assert delete(client,record).status_code==404
    assert repo.loads==loads and repo.writes==1
    assert client.get('/api/history').json()['total']==0


def test_version_conflicts_duplicate_month_and_idempotence(system):
    client,storage,repo,*_=system;login(client)
    row=save(client,'2026-10');other=save(client,'2026-09');request=body(row,current_meter=150)
    url='/api/history/'+row['record_id']
    first=client.put(url,json=request);assert first.status_code==200
    writes=repo.writes;loads=repo.loads
    assert client.put(url,json=request).json()['replayed']
    assert repo.writes==writes and repo.loads==loads
    assert client.put(url,json=request|{'current_meter':160}).status_code==409
    assert edit(client,row,current_meter=170).status_code==409
    assert delete(client,row).status_code==409
    latest=first.json()['record']
    assert edit(client,latest,billing_month=other['billing_month']).status_code==409
    assert repo.writes==writes


@pytest.mark.parametrize('removing',[False,True])
@pytest.mark.parametrize('committed',[False,True])
def test_timeout_retry_reconciles_and_cache_never_stale(system,removing,committed):
    client,storage,repo,cache,_=system;login(client);row=save(client,'2026-10')
    data=body(row,current_meter=250) if not removing else {'expected_updated_at':row['updated_at'],'request_id':str(uuid4())}
    method='DELETE' if removing else 'PUT';url='/api/history/'+row['record_id']
    repo.fail_after=committed;repo.fail_before=not committed
    assert client.request(method,url,json=data).status_code==503
    assert cache.get(storage.cache_key) is None
    view=client.get('/api/history').json()
    assert view['total']==(0 if removing and committed else 1)
    if committed and not removing: assert view['records'][0]['units_used']==250
    repo.fail_after=repo.fail_before=False
    assert client.request(method,url,json=data).status_code==200
    assert repo.writes==2  # creation plus exactly one successful mutation
    assert client.request(method,url,json=data).json()['replayed']


def test_concurrent_stale_edit_and_delete_one_winner(system):
    client,storage,repo,*_=system;login(client);row=save(client,'2026-10')
    def call(i):
        data=EditInput(**body(row,current_meter=110+i))
        try:mutate(storage,'user-a',row['record_id'],data);return 200
        except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(call,range(8)))
    assert results.count(200)==1 and results.count(409)==7 and repo.writes==2


def test_auth_origin_and_validation(system):
    client,*_=system;login(client);row=save(client,'2026-10');url='/api/history/'+row['record_id']
    for changes in [{'current_meter':-1},{'previous_meter':200},{'current_meter':1.5},{'unit_price':0},{'service_charge':-1},{'billing_month':'2026-13'},{'user_id':'user-b'},{'total_cost':0}]:
        assert client.put(url,json=body(row,**changes)).status_code==422
    assert client.put(url,json=body(row),headers={'Origin':'https://evil.example'}).status_code==403
    assert client.request('DELETE',url,json={'request_id':str(uuid4())}).status_code==422
    client.cookies.clear();assert client.put(url,json=body(row)).status_code==401
    login(client,'admin');assert client.put(url,json=body(row)).status_code==403


def test_advice_context_version_and_cache_follow_mutation(advice):
    client,ai,provider,*_=advice
    first=client.post('/api/advice/chat',json=payload()).json()
    record=client.get('/api/history').json()['records'][0]
    r=edit(client,record,current_meter=200);assert r.status_code==200,r.text
    context=client.get('/api/advice/context?month=2026-10').json()
    assert context['version']!=first['context']['version'] and Decimal(context['facts']['bill']['total_cost'])==1650
    second=client.post('/api/advice/chat',json=payload()).json()
    assert second['source']=='gemini' and len(provider.calls)==2
    assert delete(client,r.json()['record']).status_code==200
    context=client.get('/api/advice/context?month=2026-10').json()
    assert context['facts']['bill'] is None and context['version']!=second['context']['version']


def test_shared_source_cooldown_on_sheet_429(system,monkeypatch):
    import httpx
    from gspread.exceptions import APIError
    client,storage,repo,cache,_=system;login(client);row=save(client,'2026-10');calls=[]
    def fail():
        calls.append(1);raise APIError(httpx.Response(429,json={'error':{'code':429,'message':'quota','status':'RESOURCE_EXHAUSTED'}}))
    monkeypatch.setattr(repo,'load_indexed',fail)
    for _ in range(3):assert edit(client,row,current_meter=200).status_code==503
    assert len(calls)==1
    cache.delete(storage.cache_key)
    assert client.get('/api/history').status_code==503 and len(calls)==1


def test_external_change_detected_and_month_move_updates_metadata(system):
    client,storage,repo,cache,_=system;login(client);row=save(client,'2026-10')
    repo.records[0]=repo.records[0].model_copy(update={'updated_at':'2026-10-23T00:00:00+00:00'})
    assert edit(client,row,current_meter=300).status_code==409
    fresh=client.get('/api/history').json()['records'][0]
    assert fresh['updated_at']!=row['updated_at']
    moved=edit(client,fresh,billing_month='2025-12');assert moved.status_code==200
    assert client.get('/api/history?year=2026').json()['total']==0
    assert client.get('/api/history').json()['available_years']==[2025]


def test_cache_refresh_failure_after_commit_reconciles(system,monkeypatch):
    from redis.exceptions import ConnectionError
    client,storage,repo,cache,_=system;login(client);row=save(client,'2026-10');data=body(row,current_meter=240)
    original=storage.cache_records
    def fail(*args):raise ConnectionError('cache refresh failed')
    monkeypatch.setattr(storage,'cache_records',fail)
    result=client.put('/api/history/'+row['record_id'],json=data)
    assert result.status_code==200 and repo.records[0].units_used==240
    assert cache.get(storage.cache_key) is None
    monkeypatch.setattr(storage,'cache_records',original)
    assert client.put('/api/history/'+row['record_id'],json=data).json()['replayed']
    assert repo.writes==2 and storage.cached()[0].units_used==240


def test_ambiguous_commit_reconciliation_accepts_sheets_numeric_normalization(system):
    client,storage,repo,cache,_=system;login(client);row=save(client,'2026-10');data=body(row,current_meter=200,unit_price='8.0000',service_charge='50.00')
    repo.fail_after=True
    assert client.put('/api/history/'+row['record_id'],json=data).status_code==503
    repo.fail_after=False
    current=repo.records[0]
    repo.records[0]=current.model_copy(update={k:current.model_dump()[k].normalize() for k in ('unit_price','service_charge','energy_cost','total_cost')})
    response=client.put('/api/history/'+row['record_id'],json=data)
    assert response.status_code==200,response.text
    assert response.json()['replayed'] and repo.writes==2


def test_mutation_rate_limit_is_separate_per_owner(system):
    client,storage,repo,*_=system;login(client);row=save(client,'2026-10')
    for i in range(10):
        result=edit(client,row,current_meter=101+i);assert result.status_code==200
        row=result.json()['record']
    assert edit(client,row,current_meter=999).status_code==429
    login(client,'user-b');other=save(client,'2026-10')
    assert edit(client,other,current_meter=200).status_code==200


def test_repository_indexes_holes_and_updates_exact_row():
    from types import SimpleNamespace
    from app.electricity.repository import SheetRepository, HEADERS
    from app.electricity.schemas import ElectricityRecord
    def record(owner):return ElectricityRecord(billing_month='2026-10',previous_meter=0,current_meter=100,unit_price='8',service_charge='50',
        record_id=str(uuid4()),user_id=owner,units_used=100,energy_cost='800',total_cost='850',created_at='2026-10-01T00:00:00+00:00',updated_at='2026-10-01T00:00:00+00:00')
    a,b=record('user-a'),record('user-b')
    values=[HEADERS,[a.model_dump(mode='json')[h] for h in HEADERS],[],[b.model_dump(mode='json')[h] for h in HEADERS]]
    batches=[]
    client=SimpleNamespace(values_get=lambda *args,**kwargs:{'values':values},batch_update=lambda _,body:batches.append(body))
    repo=SheetRepository();repo.connection=lambda:client;repo.local=SimpleNamespace(sheet_id=123)
    rows,positions,next_row=repo.load_indexed()
    assert positions=={a.record_id:1,b.record_id:3} and next_row==4
    repo.replace(b,positions[b.record_id],lambda:None)
    update=batches[-1]['requests'][0]['updateCells']
    assert update['range']['startRowIndex']==3 and update['range']['endColumnIndex']==12
    assert update['rows'][0]['values'][1]['userEnteredValue']['stringValue']=='user-b'
    repo.remove(positions[a.record_id],lambda:None)
    clear=batches[-1]['requests'][0]['updateCells']
    assert clear['range']['startRowIndex']==1 and clear['rows'][0]['values']==[{}]*12


def test_delete_last_row_on_last_page_clamps_page(system):
    client,*_=system;login(client)
    records=[save(client,f'2026-{month:02d}') for month in range(1,8)]
    page=client.get('/api/history?page=2').json();assert page['page']==2
    assert delete(client,page['records'][0]).status_code==200
    refreshed=client.get('/api/history?page=2').json()
    assert refreshed['page']==1 and refreshed['total']==6 and refreshed['total_pages']==1
