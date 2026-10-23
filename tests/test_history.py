from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import pytest
from redis.exceptions import ConnectionError
from conftest import login


def save(client, month, units=100, charge='0'):
    response = client.post('/api/electricity', json=dict(billing_month=month, previous_meter=0,
        current_meter=units, unit_price='1', service_charge=charge))
    assert response.status_code == 201, response.text
    return response.json()['record']


def test_history_new_save_visible_and_warm_cache(system):
    client, _, repo, _, _ = system
    login(client)
    assert client.get('/api/history').json()['total'] == 0
    record = save(client, '2026-10')
    loads = repo.loads
    response = client.get('/api/history')
    assert response.headers['cache-control'] == 'no-store'
    data = response.json()
    assert data['records'][0]['record_id'] == record['record_id']
    assert data['available_years'] == [2026] and data['total'] == 1
    for _ in range(10):
        assert client.get('/api/history').status_code == 200
    assert repo.loads == loads


def test_previous_calendar_month_before_filters_and_page(system):
    client, *_ = system
    login(client)
    save(client, '2025-12', 100)
    save(client, '2026-01', 125)
    save(client, '2026-02', 100)
    save(client, '2026-04', 130)
    data = client.get('/api/history?year=2026&q=มกราคม&page_size=1').json()
    assert Decimal(data['records'][0]['change_percent']) == 25
    records = client.get('/api/history').json()['records']
    assert records[0]['change_percent'] is None  # Missing March, not previous available row.
    assert Decimal(records[1]['change_percent']) == -20
    assert records[-1]['change_percent'] is None


def test_zero_previous_and_unchanged_rounding(system):
    client, *_ = system
    login(client)
    save(client, '2026-01', 0)
    save(client, '2026-02', 100)
    save(client, '2026-03', 100)
    save(client, '2026-04', 101)
    records = client.get('/api/history').json()['records']
    assert Decimal(records[0]['change_percent']) == 1
    assert Decimal(records[1]['change_percent']) == 0
    assert records[2]['change_percent'] is None


@pytest.mark.parametrize('query', ['ตุลาคม','ต.ค.','2569','๒๕๖๙','2026-10','10/2569','ตุลาคม 2569'])
def test_search_formats(system, query):
    client, *_ = system
    login(client)
    save(client, '2026-10')
    assert client.get('/api/history',params={'q':query}).json()['total'] == 1


def test_pagination_years_and_empty(system):
    client, *_ = system
    login(client)
    for month in range(1,9): save(client, f'2026-{month:02d}')
    save(client, '2025-12')
    data = client.get('/api/history?year=2026&page=2&page_size=6').json()
    assert data['total'] == 8 and data['total_pages'] == 2
    assert [r['billing_month'] for r in data['records']] == ['2026-02','2026-01']
    assert data['available_years'] == [2026,2025]
    assert client.get('/api/history?page=999').json()['page'] == 2
    empty = client.get('/api/history?q=unknown').json()
    assert empty['total'] == 0 and empty['total_pages'] == 0 and empty['records'] == []


def test_owner_metadata_comparison_and_revocation(system):
    client, _, _, _, users = system
    assert client.get('/api/history').status_code == 401
    login(client,'user-b')
    save(client, '2024-12')
    login(client)
    save(client, '2025-01',150)
    data = client.get('/api/history').json()
    assert data['available_years'] == [2025] and data['total'] == 1
    assert data['records'][0]['user_id'] == 'user-a' and data['records'][0]['change_percent'] is None
    users['user-a']['status'] = 'inactive'
    assert client.get('/api/history').status_code in (401,403)
    login(client,'admin')
    assert client.get('/api/history').status_code == 403


@pytest.mark.parametrize('query',['page=0','page_size=0','page_size=101','year=0','year=10000','page=abc','q='+'x'*101])
def test_bounds(system,query):
    client, *_ = system
    login(client)
    assert client.get('/api/history?'+query).status_code == 422


def test_storage_failure_retry(system,monkeypatch):
    client, _, repo, cache, _ = system
    login(client)
    monkeypatch.setattr(repo,'load',lambda: (_ for _ in ()).throw(TimeoutError()))
    response = client.get('/api/history')
    assert response.status_code == 503 and response.headers['retry-after'] == '5'
    original_get = cache.get
    def failed_get(key, *args):
        if key.startswith('test:electricity'):
            raise ConnectionError()
        return original_get(key, *args)
    monkeypatch.setattr(cache,'get',failed_get)
    assert client.get('/api/history').status_code == 503


def test_concurrent_history_cold_cache_and_rounding(system):
    client, service, repo, cache, _ = system
    login(client)
    save(client, '2026-01', 2000)
    save(client, '2026-02', 2001)
    cache.delete(service.cache_key)
    before = repo.loads
    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(lambda _: client.get('/api/history?page_size=1'), range(40)))
    assert all(response.status_code == 200 for response in responses)
    assert all(Decimal(response.json()['records'][0]['change_percent']) == Decimal('0.1') for response in responses)
    assert repo.loads == before + 1
