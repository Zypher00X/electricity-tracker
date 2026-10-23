from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import pytest
from conftest import login
from test_history import save
from test_history_mutations import edit,delete
from app.dashboard import routes

@pytest.fixture
def dash(system):
    system[0].app.include_router(routes.router)
    return system

def test_totals_calendar_average_and_breakdown(dash):
    client,storage,repo,*_=dash;login(client)
    save(client,'2026-03',9999)  # Outside the six calendar months ending October.
    save(client,'2026-05',100);save(client,'2026-09',200);save(client,'2026-10',300,'50')
    r=client.get('/api/dashboard');assert r.status_code==200,r.text
    d=r.json();assert d['month']=='2026-10' and d['period_start']=='2026-05'
    assert d['units_used']==300 and Decimal(d['total_cost'])==350
    assert Decimal(d['units_change_percent'])==50 and Decimal(d['cost_change_percent'])==75
    assert d['average_bill_count']==3 and Decimal(d['average_cost'])==Decimal('216.67')
    assert Decimal(d['versus_average_percent'])==Decimal('61.5')
    assert [x['total_cost'] for x in d['series']]==['100',None,None,None,'200','350'] or [Decimal(x['total_cost']) if x['total_cost'] is not None else None for x in d['series']]==[100,None,None,None,200,350]
    assert [Decimal(x['percent']) for x in d['cost_breakdown']]==[Decimal('85.7'),Decimal('14.3')]
    assert len(d['cost_breakdown'])==2 and r.headers['cache-control']=='no-store'

def test_owner_isolation_default_and_explicit_missing_month(dash):
    client,storage,repo,*_=dash;login(client);save(client,'2026-10',100)
    login(client,'user-b');save(client,'2025-01',500)
    d=client.get('/api/dashboard').json();assert d['available_months']==['2025-01'] and d['month']=='2025-01'
    d=client.get('/api/dashboard?month=2026-10').json()
    assert not d['has_bill'] and d['total_cost'] is None and d['average_cost'] is None
    assert all(x['total_cost'] is None for x in d['series']) and d['cost_breakdown']==[]

def test_zero_bill_and_missing_previous_do_not_fabricate_comparisons(dash):
    client,*_=dash;login(client);save(client,'2026-01',0);save(client,'2026-02',100);save(client,'2026-04',200)
    zero=client.get('/api/dashboard?month=2026-01').json()
    assert zero['has_bill'] and Decimal(zero['total_cost'])==0 and zero['cost_breakdown'][0]['percent'] is None
    assert zero['versus_average_percent'] is None and zero['average_bill_count']==1
    assert client.get('/api/dashboard?month=2026-02').json()['cost_change_percent'] is None
    assert client.get('/api/dashboard?month=2026-04').json()['cost_change_percent'] is None

def test_create_edit_delete_refresh_same_shared_cache(dash):
    client,storage,repo,*_=dash;login(client)
    assert not client.get('/api/dashboard').json()['has_bill']
    row=save(client,'2026-10',100)
    assert Decimal(client.get('/api/dashboard').json()['total_cost'])==100
    changed=edit(client,row,current_meter=200).json()['record']
    assert Decimal(client.get('/api/dashboard').json()['total_cost'])==200
    assert delete(client,changed).status_code==200
    assert not client.get('/api/dashboard?month=2026-10').json()['has_bill']

def test_warm_cache_and_cold_read_coalescing(dash):
    client,storage,repo,cache,_=dash;login(client);save(client,'2026-10')
    before=repo.loads
    for _ in range(15):assert client.get('/api/dashboard').status_code==200
    assert repo.loads==before
    cache.delete(storage.cache_key)
    from app.dashboard.service import dashboard
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(lambda _:dashboard(storage,'user-a'),range(16)))
    assert repo.loads==before+1 and all(r['units_used']==100 for r in results)

def test_validation_roles_and_failure_recovery(dash,monkeypatch):
    client,storage,repo,cache,_=dash
    assert client.get('/api/dashboard').status_code==401
    login(client,'admin');assert client.get('/api/dashboard').status_code==403
    login(client)
    for value in ['2026-13','0000-01','bad']:
        assert client.get('/api/dashboard',params={'month':value}).status_code==422
    assert client.get('/api/dashboard?month=0001-01').status_code==200
    cache.delete(storage.cache_key);original=repo.load
    def fail():raise TimeoutError('source failed')
    monkeypatch.setattr(repo,'load',fail)
    r=client.get('/api/dashboard');assert r.status_code==503 and r.headers['retry-after']=='10'
    monkeypatch.setattr(repo,'load',original)
    assert client.get('/api/dashboard').status_code==200
