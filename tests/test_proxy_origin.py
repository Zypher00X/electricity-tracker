"""The route-level guard must accept public HTTPS behind an HTTP proxy."""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.http_security import HTTPSecurity
from app.electricity.routes import same_origin


@pytest.fixture
def proxied(monkeypatch):
    public = 'https://powertrack-demo.onrender.com'
    monkeypatch.setenv('PUBLIC_ORIGIN', public)
    app = FastAPI()
    app.add_middleware(HTTPSecurity, public_origin=public, production=True)

    @app.post('/mutation', dependencies=[Depends(same_origin)])
    def mutation():
        return {'ok': True}

    return TestClient(app, base_url='http://powertrack-demo.onrender.com')


def test_https_public_origin_accepted_through_both_guards(proxied):
    for source in ('https://powertrack-demo.onrender.com',
                   'https://powertrack-demo.onrender.com:443'):
        result = proxied.post('/mutation', json={}, headers={
            'Origin': source, 'Sec-Fetch-Site': 'same-origin'})
        assert result.status_code == 200


@pytest.mark.parametrize('source', [
    'https://evil.example', 'null',
    'http://powertrack-demo.onrender.com',
    'https://powertrack-demo.onrender.com.evil.example',
    'https://powertrack-demo.onrender.com/path',
])
def test_foreign_or_invalid_origin_still_denied(proxied, source):
    assert proxied.post('/mutation', json={}, headers={'Origin': source}).status_code == 403


def test_headers_cannot_override_configured_origin(proxied):
    assert proxied.post('/mutation', json={}, headers={
        'Origin': 'https://evil.example',
        'X-Forwarded-Host': 'evil.example',
        'X-Forwarded-Proto': 'https'}).status_code == 403
    assert proxied.post('/mutation', json={}, headers={
        'Origin': 'https://powertrack-demo.onrender.com',
        'Sec-Fetch-Site': 'cross-site'}).status_code == 403


def test_proxy_guard_keeps_json_requirement_and_cli_support(proxied):
    assert proxied.post('/mutation', json={}).status_code == 200
    assert proxied.post('/mutation', content='plain text').status_code == 415
