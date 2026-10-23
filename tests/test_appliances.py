import copy
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from decimal import Decimal
import pytest
from app.appliances import routes
from app.appliances.service import Service
from conftest import login

class MemoryRepository:
    def __init__(self):
        self.loads=self.writes=0
        self.fail=False
        self.data=[{'rows':[],'next':1,'sheet':{}},{'rows':[],'next':1,'sheet':{}}]
    def load(self):
        self.loads+=1
        return copy.deepcopy(self.data)
    def commit(self,changes,guard):
        guard()
        if self.fail: raise TimeoutError()
        for dataset,record,index,headers in changes:
            slot=0 if 'appliance_name' in record else 1
            target=self.data[slot]
            target['rows']=[r for r in target['rows'] if r['_row']!=index]+[dict(record,_row=index)]
            target['next']=max(target['next'],index+1)
        self.writes+=1

@pytest.fixture
def appliances(system,monkeypatch):
    client,_,_,cache,_=system
    repo=MemoryRepository();service=Service(repo,cache,'test:appliances',ttl=30)
    monkeypatch.setattr(routes,'service',service)
    client.app.include_router(routes.router)
    return client,service,repo,cache

BASE=dict(billing_month='2026-10',appliance_name='Fixture',category='computer',quantity=2,average_power_w='200',hours_per_day='8',days_used=20,source='measured')
def post(client,payload=None,key=None):
    return client.post('/api/appliances',json=payload or BASE,headers={'Idempotency-Key':key or str(uuid4())})

def test_create_rows_cache_and_visibility(appliances):
    client,service,repo,cache=appliances;login(client)
    response=post(client);assert response.status_code==201,response.text
    result=response.json()['record'];assert Decimal(result['estimated_kwh'])==64
    assert len(repo.data[0]['rows'])==len(repo.data[1]['rows'])==1
    assert repo.data[1]['rows'][0]['user_id']=='user-a'
    assert repo.data[1]['rows'][0]['appliance_id']==repo.data[0]['rows'][0]['appliance_id']
    loads=repo.loads
    assert client.get('/api/appliances?billing_month=2026-10').json()['records'][0]['id']==result['id']
    assert repo.loads==loads
    assert client.get('/api/appliances?billing_month=2026-09').json()['records']==[]

@pytest.mark.parametrize('changes',[{'quantity':0},{'quantity':True},{'hours_per_day':25},{'days_used':32},{'billing_month':'2026-02','days_used':29},{'rated_power_w':0},{'average_power_w':-1},{'source':'bad'},{'category':'bad'},{'category':'other'},{'estimated_kwh':'5'},{'user_id':'user-b'},{'hours_per_day':True},{'average_power_w':'NaN'},{'monthly_kwh_per_unit':'Infinity'},{'appliance_name':'  '}])
def test_validation(appliances,changes):
    client,_,repo,_=appliances;login(client)
    assert post(client,BASE|changes).status_code==422
    assert repo.writes==0

@pytest.mark.parametrize('payload,expected',[
    (dict(billing_month='2026-10',appliance_name='Unknown',category='air_conditioner'),None),
    (BASE|{'source':'unknown'},None),(BASE|{'hours_per_day':None},None),
    (BASE|{'hours_per_day':'0'},Decimal('0')),
    (BASE|{'estimation_method':'monthly_kwh','monthly_kwh_per_unit':'35.12345'},'invalid'),
    (BASE|{'estimation_method':'monthly_kwh','monthly_kwh_per_unit':'35.1234','source':'energy_label'},Decimal('70.2468')),
    (BASE|{'category':'other','category_custom':'เครื่องเย็บผ้า'},Decimal('64'))])
def test_optional_methods(appliances,payload,expected):
    client,*_=appliances;login(client);response=post(client,payload)
    if expected=='invalid':assert response.status_code==422;return
    assert response.status_code==201,response.text
    record=response.json()['record']
    assert (None if record['estimated_kwh'] is None else Decimal(record['estimated_kwh']))==expected
    if payload.get('category')=='other':assert record['category_custom']=='เครื่องเย็บผ้า'


def test_owner_update_revision_cancel(appliances):
    client,_,repo,_=appliances;login(client)
    record=post(client).json()['record'];uid=record['id']
    login(client,'user-b')
    assert client.get('/api/appliances?billing_month=2026-10').json()['records']==[]
    assert client.put('/api/appliances/'+uid,json=BASE|{'revision':1},headers={'Idempotency-Key':str(uuid4())}).status_code==404
    login(client)
    edited=client.put('/api/appliances/'+uid,json=BASE|{'revision':1,'quantity':3},headers={'Idempotency-Key':str(uuid4())})
    assert edited.status_code==200 and Decimal(edited.json()['record']['estimated_kwh'])==96
    assert client.put('/api/appliances/'+uid,json=BASE|{'revision':1},headers={'Idempotency-Key':str(uuid4())}).status_code==409
    cancelled=client.post('/api/appliances/'+uid+'/cancel',json={'revision':2},headers={'Idempotency-Key':str(uuid4())})
    assert cancelled.status_code==200 and cancelled.json()['record']['status']=='cancelled'
    assert client.get('/api/appliances?billing_month=2026-10').json()['records']==[]
    assert len(repo.data[1]['rows'])==1 and repo.data[1]['rows'][0]['status']=='cancelled'


def test_idempotency_concurrent_and_cache_coalescing(appliances):
    client,service,repo,cache=appliances;login(client);key=str(uuid4())
    with ThreadPoolExecutor(max_workers=10) as pool:responses=list(pool.map(lambda _:post(client,key=key),range(20)))
    assert all(r.status_code==201 for r in responses)
    assert len({r.json()['record']['id'] for r in responses})==1 and repo.writes==1
    assert post(client,BASE|{'quantity':4},key).status_code==409
    cache.delete(service.cache_key);before=repo.loads
    with ThreadPoolExecutor(max_workers=10) as pool:responses=list(pool.map(lambda _:client.get('/api/appliances?billing_month=2026-10'),range(20)))
    assert all(r.status_code==200 for r in responses) and repo.loads==before+1


def test_security_and_failure(appliances):
    client,_,repo,_=appliances
    assert client.get('/api/appliances?billing_month=2026-10').status_code==401
    login(client,'admin');assert post(client).status_code==403
    login(client)
    assert client.post('/api/appliances',json=BASE,headers={'Idempotency-Key':str(uuid4()),'Origin':'https://evil.example'}).status_code==403
    repo.fail=True;assert post(client).status_code==503
    assert repo.writes==0


def test_create_retry_after_later_edit_never_duplicates(appliances):
    client,_,repo,_=appliances;login(client)
    key=str(uuid4());record=post(client,key=key).json()['record']
    response=client.put('/api/appliances/'+record['id'],json=BASE|{'revision':1,'quantity':3},headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==200
    assert post(client,key=key).status_code==409
    assert len(repo.data[1]['rows'])==1


def test_repository_atomic_two_sheets_and_numeric_blank_cells():
    from unittest.mock import Mock
    from app.appliances.repository import Repository, APPLIANCE_HEADERS, USAGE_HEADERS
    repo=Repository();client=Mock();repo.client=lambda:client
    guard=Mock()
    a={'sheet':{'properties':{'sheetId':1,'gridProperties':{'rowCount':2}},'tables':[{'tableId':'a','range':{'endRowIndex':2}}]}}
    u={'sheet':{'properties':{'sheetId':2,'gridProperties':{'rowCount':2}},'tables':[{'tableId':'u','range':{'endRowIndex':2}}]}}
    repo.commit([(a,{'appliance_name':'=literal','quantity':2},2,APPLIANCE_HEADERS),(u,{'estimated_kwh':'64.0000','revision':1},2,USAGE_HEADERS)],guard)
    guard.assert_called_once()
    client.batch_update.assert_called_once()
    requests=client.batch_update.call_args.args[1]['requests']
    assert sum('updateCells' in request for request in requests)==2
    assert sum('updateTable' in request for request in requests)==2
    cells=[request['updateCells']['rows'][0]['values'] for request in requests if 'updateCells' in request]
    assert cells[0][2]['userEnteredValue']=={'stringValue':'=literal'}
    assert cells[1][15]['userEnteredValue']=={'numberValue':64.0}
    assert cells[1][7]=={}  # Unknown watts is a blank, not zero.
