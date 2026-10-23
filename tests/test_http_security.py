import importlib
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from app.core.http_security import HTTPSecurity, origin
from conftest import login


@pytest.fixture
def boundary():
    app = FastAPI()
    app.add_middleware(HTTPSecurity, max_body=100)
    @app.post('/echo')
    async def echo(request: Request):
        return {'length': len(await request.body())}
    return TestClient(app)


def test_origin_and_fetch_metadata_reject_cross_site_writes(boundary):
    assert boundary.post('/echo', json={}, headers={'Origin': 'http://testserver'}).status_code == 200
    for value in ('https://evil.example', 'null', 'http://testserver.evil.example', 'http://testserver/path'):
        assert boundary.post('/echo', json={}, headers={'Origin': value}).status_code == 403
    assert boundary.post('/echo', json={}, headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert boundary.post('/echo', json={}).status_code == 200  # Non-browser clients still work.
    assert origin('https://EXAMPLE.com:443') == origin('https://example.com')


def test_bodies_bounded_even_without_content_length_and_security_headers(boundary):
    for body in (b'a' * 101, iter([b'a' * 60, b'b' * 60])):
        response = boundary.post('/echo', content=body)
        assert response.status_code == 413
        assert response.headers['x-content-type-options'] == 'nosniff'
    assert boundary.post('/echo', content=b'ok').json()['length'] == 2
    response = boundary.get('/missing')
    assert response.headers['x-frame-options'] == 'DENY'
    assert "script-src 'self';" in response.headers['content-security-policy']


def test_sheets_diagnostic_is_admin_only_and_errors_do_not_leak(system, monkeypatch):
    _, _, _, _, users = system
    frontend = str(Path(__file__).resolve().parents[1] / 'Front__end')
    with patch('fastapi.staticfiles.StaticFiles', side_effect=lambda **kw: StaticFiles(directory=frontend)):
        main = importlib.import_module('app.main')
    calls = []
    def diagnostic():
        calls.append(True)
        raise RuntimeError('private-provider-error-marker')
    monkeypatch.setattr(main, 'test_google_sheets_connection', diagnostic)
    client = TestClient(main.app)
    assert client.get('/api/google-sheets/health').status_code == 401
    login(client)
    assert client.get('/api/google-sheets/health').status_code == 403
    assert not calls
    login(client, 'admin')
    result = client.get('/api/google-sheets/health')
    assert result.status_code == 503 and 'private-provider-error-marker' not in result.text
    assert result.headers['cache-control'] == 'no-store'
