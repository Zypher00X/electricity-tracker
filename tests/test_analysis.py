from decimal import Decimal
from uuid import uuid4
import pytest
from conftest import login
from test_appliances import appliances, BASE, post
from app.analysis.routes import router

@pytest.fixture
def analysis(appliances):
    client,*_=appliances
    client.app.include_router(router)
    return appliances

def bill(client,month,units=100,price='8',charge='50'):
    response=client.post('/api/electricity',json=dict(billing_month=month,previous_meter=0,current_meter=units,unit_price=price,service_charge=charge))
    assert response.status_code==201,response.text
    return response.json()['record']

def get(client,**params):
    response=client.get('/api/analysis',params=params)
    assert response.status_code==200,response.text
    return response.json()

def test_analysis_calculations_and_sources(analysis):
    client,*_=analysis;login(client)
    bill(client,'2026-09',100);bill(client,'2026-10',125)
    usage=post(client).json()['record']
    data=get(client,months=3,end_month='2026-10')
    assert data['start_month']=='2026-08' and len(data['series'])==3
    assert data['series'][0]['units_used'] is None
    assert Decimal(data['latest']['total_cost'])==1050
    assert Decimal(data['latest']['cost_change_percent'])==Decimal('23.5')
    assert Decimal(data['latest']['units_change_percent'])==25
    assert data['highest']==dict(month='2026-10',units_used=125)
    assert data['lowest']==dict(month='2026-09',units_used=100)
    assert Decimal(data['appliances'][0]['estimated_kwh'])==64
    assert Decimal(data['appliance_summary']['difference_kwh'])==-61
    assert sum(Decimal(part['amount']) for part in data['cost_breakdown'])==1050
    assert data['appliances'][0]['appliance_id']==usage['appliance_id']


def test_empty_unknown_zero_and_gap(analysis):
    client,*_=analysis;login(client)
    empty=get(client,months=3,end_month='2026-10')
    assert empty['latest'] is None and not empty['has_data']
    assert all(r['units_used'] is None for r in empty['series'])
    bill(client,'2026-08',0,charge='0');bill(client,'2026-09',0,charge='0')
    data=get(client,months=3,end_month='2026-10')
    assert data['latest']['cost_change_percent'] is None
    assert data['latest']['units_change_percent'] is None
    assert all(part['percent'] is None for part in data['cost_breakdown'])
    assert data['series'][0]['units_used']==0 and data['series'][-1]['units_used'] is None
    unknown=BASE|{'source':'unknown'};post(client,unknown)
    data=get(client,end_month='2026-10')
    assert data['appliance_summary']['unknown_items']==1
    assert data['appliance_summary']['estimated_kwh'] is None


def test_exact_previous_month_and_year_boundary(analysis):
    client,*_=analysis;login(client)
    bill(client,'2025-12',100,price='1',charge='0');bill(client,'2026-01',90,price='1',charge='0')
    data=get(client,months=3,end_month='2026-01')
    assert Decimal(data['latest']['cost_change_percent'])==-10
    bill(client,'2026-03',99,price='1',charge='0')
    assert get(client,months=3,end_month='2026-03')['latest']['cost_change_percent'] is None


def test_owner_and_cancelled_orphan_exclusion(analysis):
    client,_,repo,cache=analysis;login(client,'user-b')
    bill(client,'2027-01',500);post(client,BASE|{'billing_month':'2027-01'})
    login(client)
    data=get(client,end_month='2026-10')
    assert data['available_months']==[] and data['appliances']==[]
    usage=post(client).json()['record']
    assert get(client,end_month='2026-10')['appliance_summary']['items']==1
    client.post('/api/appliances/'+usage['id']+'/cancel',json={'revision':1},headers={'Idempotency-Key':str(uuid4())})
    assert get(client,end_month='2026-10')['appliance_summary']['items']==0
    usage=post(client).json()['record'];repo.data[0]['rows']=[];cache.flushdb()
    # flushdb revokes auth too; login again, then orphan references are ignored.
    login(client)
    assert get(client,end_month='2026-10')['appliance_summary']['items']==0


def test_live_changes_visible_and_cache_io(analysis):
    client,service,repo,cache=analysis;login(client)
    get(client,end_month='2026-10')  # populate empty caches
    bill(client,'2026-10',100)
    saved=post(client).json()['record'];loads=repo.loads
    assert get(client,end_month='2026-10')['latest']['units_used']==100
    for _ in range(5):get(client,end_month='2026-10')
    assert repo.loads==loads
    edited=client.put('/api/appliances/'+saved['id'],json=BASE|{'revision':1,'quantity':3},headers={'Idempotency-Key':str(uuid4())})
    assert edited.status_code==200
    assert Decimal(get(client,end_month='2026-10')['appliances'][0]['estimated_kwh'])==96


@pytest.mark.parametrize('params',[{'months':0},{'months':4},{'months':100},{'end_month':'2026-13'},{'end_month':'0000-01'},{'end_month':'0001-01','months':12}])
def test_analysis_input_bounds(analysis,params):
    client,*_=analysis;login(client)
    assert client.get('/api/analysis',params=params).status_code==422


def test_analysis_auth_and_storage_failure(analysis,monkeypatch):
    client,service,repo,cache=analysis
    assert client.get('/api/analysis').status_code==401
    login(client,'admin');assert client.get('/api/analysis').status_code==403
    login(client)
    monkeypatch.setattr(repo,'load',lambda: (_ for _ in ()).throw(TimeoutError()))
    response=client.get('/api/analysis')
    assert response.status_code==503 and response.headers['retry-after']=='5'


def test_archived_identity_keeps_historical_snapshot_and_recomputes(analysis):
    client,service,repo,cache=analysis;login(client)
    saved=post(client).json()['record']
    repo.data[0]['rows'][0]['status']='archived'
    repo.data[0]['rows'][0]['appliance_name']='Changed default name'
    repo.data[1]['rows'][0]['estimated_kwh']='99999'
    cache.delete(service.cache_key)
    data=get(client,end_month='2026-10')
    assert data['appliances'][0]['name']==BASE['appliance_name']
    assert Decimal(data['appliances'][0]['estimated_kwh'])==64
    assert data['latest'] is None and data['appliance_summary']['meter_kwh'] is None


def test_foreign_master_reference_never_joins(analysis):
    client,service,repo,cache=analysis;login(client)
    post(client)
    repo.data[0]['rows'][0]['user_id']='user-b'
    cache.delete(service.cache_key)
    assert get(client,end_month='2026-10')['appliances']==[]
