import copy
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import Mock
import pytest
from app.settings import routes
from app.settings.schemas import SettingsRecord
from app.settings.service import Service
from conftest import login

class MemorySettings:
    def __init__(self):self.rows=[];self.loads=self.writes=0;self.fail=False;self.fail_after=False
    def load(self):self.loads+=1;return copy.deepcopy(self.rows),len(self.rows)+1
    def save(self,record,row,guard):
        guard()
        if self.fail:raise TimeoutError()
        self.rows=[(i,r) for i,r in self.rows if i!=row]+[(row,copy.deepcopy(record))];self.writes+=1
        if self.fail_after:raise TimeoutError()

@pytest.fixture
def settings(system,monkeypatch):
    client,_,_,cache,_=system;repo=MemorySettings();service=Service(repo,cache,'test:settings',ttl=30)
    monkeypatch.setattr(routes,'service',service);client.app.include_router(routes.router)
    return client,service,repo,cache

BASE=dict(residence_type='house',occupants=2,default_unit_price='8.1234',default_service_charge='50.00',monthly_budget='1500.00',expected_updated_at=None)

def test_upsert_roundtrip_cache_and_versions(settings):
    client,_,repo,_=settings;login(client)
    assert client.get('/api/settings').json()['settings'] is None
    saved=client.put('/api/settings',json=BASE);assert saved.status_code==200,saved.text
    record=saved.json()['settings'];loads=repo.loads
    assert record['user_id']=='user-a' and record['currency']=='THB' and Decimal(record['default_unit_price'])==Decimal('8.1234')
    assert client.get('/api/settings').json()['settings']==record and repo.loads==loads
    response=client.put('/api/settings',json=BASE|{'monthly_budget':'2000','expected_updated_at':record['updated_at']})
    assert response.status_code==200
    updated=response.json()['settings'];assert updated['created_at']==record['created_at'] and updated['updated_at']!=record['updated_at']
    assert len(repo.rows)==1 and Decimal(updated['monthly_budget'])==2000
    assert client.put('/api/settings',json=BASE|{'expected_updated_at':record['updated_at']}).status_code==409

@pytest.mark.parametrize('changes',[{'occupants':0},{'occupants':1.5},{'occupants':True},{'occupants':1001},{'residence_type':'bad'},{'default_unit_price':0},{'default_unit_price':'8.12345'},{'default_unit_price':True},{'monthly_budget':-1},{'monthly_budget':'NaN'},{'monthly_budget':'Infinity'},{'default_service_charge':'1.001'},{'user_id':'other'},{'currency':'USD'},{'timezone':'UTC'},{'created_at':'fake'}])
def test_validation(settings,changes):
    client,_,repo,_=settings;login(client)
    assert client.put('/api/settings',json=BASE|changes).status_code==422
    assert repo.writes==0


def test_optional_null_zero_and_clear(settings):
    client,_,repo,_=settings;login(client)
    record=client.put('/api/settings',json={'expected_updated_at':None}).json()['settings']
    assert record['occupants'] is record['default_unit_price'] is record['monthly_budget'] is None
    response=client.put('/api/settings',json={'expected_updated_at':record['updated_at'],'default_service_charge':'0','monthly_budget':'0'})
    assert response.status_code==200
    record=response.json()['settings'];assert Decimal(record['monthly_budget'])==0 and record['default_unit_price'] is None


def test_owner_isolation_and_concurrent_create(settings):
    client,service,repo,cache=settings;login(client)
    with ThreadPoolExecutor(max_workers=8) as pool:responses=list(pool.map(lambda _:client.put('/api/settings',json=BASE),range(16)))
    assert sum(r.status_code==200 for r in responses)==1 and all(r.status_code in [200,409] for r in responses)
    assert len(repo.rows)==1
    login(client,'user-b');loads=repo.loads
    assert client.get('/api/settings').json()['settings'] is None and repo.loads==loads
    assert client.put('/api/settings',json=BASE|{'occupants':4}).status_code==200
    assert len(repo.rows)==2 and client.get('/api/settings').json()['settings']['occupants']==4


def test_cold_cache_coalesces_and_failures(settings,monkeypatch):
    client,service,repo,cache=settings;login(client)
    with ThreadPoolExecutor(max_workers=8) as pool:responses=list(pool.map(lambda _:client.get('/api/settings'),range(16)))
    assert all(r.status_code==200 for r in responses) and repo.loads==1
    repo.fail=True;assert client.put('/api/settings',json=BASE).status_code==503
    repo.fail=False;repo.fail_after=True
    assert client.put('/api/settings',json=BASE).status_code==503
    assert client.get('/api/settings').json()['settings']['occupants']==2
    assert client.put('/api/settings',json=BASE).status_code==409 and len(repo.rows)==1


def test_auth_origin_and_missing_version(settings):
    client,*_=settings
    assert client.get('/api/settings').status_code==401
    login(client,'admin');assert client.get('/api/settings').status_code==403
    login(client)
    assert client.put('/api/settings',json=BASE,headers={'Origin':'https://evil.example'}).status_code==403
    assert client.put('/api/settings',json={'residence_type':'house'}).status_code==422


def test_repository_types_blank_and_atomic_table_update():
    from app.settings.repository import Repository,HEADERS
    repo=Repository();client=Mock();repo.client=lambda:client
    client.spreadsheets_get.return_value={'sheets':[{'properties':{'title':repo.sheet_name,'sheetId':1,'gridProperties':{'rowCount':2}},'tables':[{'tableId':'x','range':{'sheetId':1,'startRowIndex':0,'endRowIndex':2,'startColumnIndex':0,'endColumnIndex':10}}]}]}
    record=SettingsRecord(user_id='a',monthly_budget='0',created_at='time',updated_at='time')
    guard=Mock();repo.save(record,1,guard);guard.assert_called_once();client.batch_update.assert_called_once()
    requests=client.batch_update.call_args.args[1]['requests'];cells=requests[0]['updateCells']['rows'][0]['values']
    assert cells[2]=={} and cells[3]=={} and cells[5]['userEnteredValue']=={'numberValue':0.0}
    assert 'updateTable' in requests[1]
