from concurrent.futures import ThreadPoolExecutor
from app.schemas.auth import RegisterRequest
from app.services import auth_service, session_service
from app.services.auth_service import EmailAlreadyExistsError


def test_concurrent_registrations_only_append_one_identity(system):
    client, service, repo, cache, users = system
    data = RegisterRequest(full_name='Concurrent Fixture', email='new@example.com', phone='0899999999', password='FixturePassword123!')
    def register(_):
        try:
            auth_service.register_user(data)
            return 'created'
        except EmailAlreadyExistsError:
            return 'duplicate'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(register, range(2)))
    assert sorted(results) == ['created', 'duplicate']
    assert sum(u['email'] == 'new@example.com' for u in users.values()) == 1


def test_registration_fails_closed_without_redis(system, monkeypatch):
    client, service, repo, cache, users = system
    from redis.exceptions import ConnectionError
    def unavailable(*a, **kw): raise ConnectionError('isolated outage')
    monkeypatch.setattr(cache, 'lock', unavailable)
    before = len(users)
    import pytest
    with pytest.raises(ConnectionError):
        auth_service.register_user(RegisterRequest(full_name='Fixture', email='new@example.com', phone='0899999999', password='FixturePassword123!'))
    assert len(users) == before
