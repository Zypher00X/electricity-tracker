from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import json
import pytest
import fakeredis
import requests
from gspread.exceptions import APIError
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from app.services.auth_user_cache import AuthUserCache,FIELDS
from app.core.storage_errors import install_storage_handlers
from app.dependencies import auth as dependencies
from conftest import login
from test_analysis import analysis
from test_appliances import appliances

USERS=[dict(user_id='a',full_name='A',email='a@example.com',phone='',role='user',status='active',password_hash='never-cache-this'),dict(user_id='b',full_name='B',email='b@example.com',phone='',role='user',status='active')]

def test_singleflight_two_accounts_no_secrets():
    redis=fakeredis.FakeRedis(decode_responses=True);loader=Mock(return_value=USERS)
    cache=AuthUserCache(redis,'test:auth',loader)
    with ThreadPoolExecutor(max_workers=20) as pool:
        users=list(pool.map(lambda i:cache.find('a' if i%2==0 else 'b'),range(80)))
    assert loader.call_count==1
    assert all(u['user_id']==('a' if i%2==0 else 'b') for i,u in enumerate(users))
    assert set(json.loads(redis.get(cache.cache_key))[0])==set(FIELDS)
    assert 'never-cache-this' not in redis.get(cache.cache_key)
    assert 0<redis.ttl(cache.cache_key)<=10


def test_status_refresh_no_stale_fallback():
    redis=fakeredis.FakeRedis(decode_responses=True);users=[dict(USERS[0])]
    cache=AuthUserCache(redis,'test:auth',lambda:users)
    assert cache.find('a')['status']=='active'
    users[0]['status']='inactive'
    assert cache.find('a')['status']=='active' # Authorized 10-second window.
    redis.pexpire(cache.cache_key,1)
    import time;time.sleep(.01)
    assert cache.find('a')['status']=='inactive'
    redis.delete(cache.cache_key)
    cache.loader=Mock(side_effect=TimeoutError())
    with pytest.raises(HTTPException) as error:cache.find('a')
    assert error.value.status_code==503


def test_missing_new_user_refreshes_old_snapshot():
    redis=fakeredis.FakeRedis(decode_responses=True);loader=Mock(side_effect=[[USERS[0]],USERS])
    cache=AuthUserCache(redis,'test:auth',loader)
    assert cache.find('a')['user_id']=='a'
    assert cache.find('b')['user_id']=='b'
    assert loader.call_count==2


def test_quota_cooldown():
    response=requests.Response();response.status_code=429
    response._content=b'{"error":{"code":429,"message":"quota","status":"RESOURCE_EXHAUSTED"}}'
    loader=Mock(side_effect=APIError(response));redis=fakeredis.FakeRedis(decode_responses=True)
    cache=AuthUserCache(redis,'test:auth',loader)
    for _ in range(5):
        with pytest.raises(HTTPException) as error:cache.find('a')
        assert error.value.status_code==503 and error.value.headers['Retry-After']=='10'
    assert loader.call_count==1


def test_mixed_pages_two_sessions_isolation_logout_and_revocation(analysis,system,monkeypatch):
    # analysis and system resolve the same function-scoped fixture dependency.
    first,_,_,redis=analysis
    users=system[4];loader=Mock(side_effect=lambda:list(users.values()))
    cache=AuthUserCache(redis,'test:auth',loader)
    monkeypatch.setattr(dependencies,'find_user_by_id',cache.find)
    second=TestClient(first.app)
    login(first);login(second,'user-b')
    first.post('/api/electricity',json={'billing_month':'2026-10','previous_meter':0,'current_meter':100,'unit_price':'8','service_charge':'50'})
    endpoints=['/api/auth/me','/api/history','/api/appliances?billing_month=2026-10','/api/analysis?end_month=2026-10']
    def read(i):
        client=first if i%2==0 else second
        response=client.get(endpoints[(i//2)%len(endpoints)])
        return i,response
    with ThreadPoolExecutor(max_workers=16) as pool:results=list(pool.map(read,range(80)))
    assert all(response.status_code==200 for _,response in results)
    for i,response in results:
        if response.request.url.path=='/api/history':assert response.json()['total']==(1 if i%2==0 else 0)
        if response.request.url.path=='/api/auth/me':assert response.json()['user']['user_id']==('user-a' if i%2==0 else 'user-b')
    assert loader.call_count==1
    old_cookie=first.cookies.get('powertrack_access_token')
    first.post('/api/auth/logout')
    first.cookies.clear()
    first.cookies.set('powertrack_access_token',old_cookie)
    assert first.get('/api/auth/me').status_code==401
    assert second.get('/api/auth/me').status_code==200
    users['user-b']['status']='inactive';redis.delete(cache.cache_key)
    assert second.get('/api/auth/me').status_code==403


def test_global_storage_error_503():
    from redis.exceptions import ConnectionError
    app=FastAPI();install_storage_handlers(app)
    @app.get('/fixture')
    def fixture():raise ConnectionError('private details')
    response=TestClient(app).get('/fixture')
    assert response.status_code==503 and 'private details' not in response.text


def test_auth_read_is_one_values_call_without_metadata(monkeypatch):
    from types import SimpleNamespace
    from app.services import auth_user_cache as module
    client=Mock()
    client.values_get.return_value={'values':[['user_id','full_name','email','phone','role','status','password_hash'],['a','A','a@example.com','','user','active','secret-hash']]}
    monkeypatch.setattr(module,'_local',SimpleNamespace())
    monkeypatch.setattr(module,'get_google_sheets_client',lambda:SimpleNamespace(http_client=client))
    result=module.load_users()
    assert result[0]['user_id']=='a' and 'password_hash' not in result[0]
    client.values_get.assert_called_once()
    client.spreadsheets_get.assert_not_called()
    module.load_users()
    client.set_timeout.assert_called_once_with((5,15))
