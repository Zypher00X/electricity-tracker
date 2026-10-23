"""Deployment contracts tested without network or production secrets."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def redis_probe(url=None, allow=False, legacy=True):
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT / 'Back__end')
    env.pop('REDIS_URL', None)
    env.pop('REDIS_ALLOW_PASSWORDLESS_PRIVATE', None)
    if url is not None:
        env['REDIS_URL'] = url
    if allow:
        env['REDIS_ALLOW_PASSWORDLESS_PRIVATE'] = 'true'
    if not legacy:
        env.pop('REDIS_PASSWORD', None)
    code = """
import json
from app.core.redis import create_redis_client
from app.electricity.service import feature_redis
clients=[create_redis_client(),feature_redis]
print(json.dumps([dict(host=c.connection_pool.connection_kwargs['host'], password=bool(c.connection_pool.connection_kwargs.get('password')), timeout=c.connection_pool.connection_kwargs['socket_timeout'], tls=c.connection_pool.connection_class.__name__) for c in clients]))
"""
    return subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True)


def test_legacy_redis_still_supported():
    r = redis_probe()
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert all(c['password'] for c in data)
    assert [c['timeout'] for c in data] == [5, 3]


def test_private_redis_requires_explicit_opt_in():
    assert redis_probe('redis://private-fixture:6379/0', legacy=False).returncode != 0
    r = redis_probe('redis://private-fixture:6379/0', allow=True, legacy=False)
    assert r.returncode == 0, r.stderr
    assert all(c['host'] == 'private-fixture' and not c['password'] for c in json.loads(r.stdout))


def test_authenticated_tls_redis_uses_ssl_client():
    r = redis_probe('rediss://default:fixture-only@example.invalid:6380/0', legacy=False)
    assert r.returncode == 0, r.stderr
    assert all(c['tls'] == 'SSLConnection' and c['password'] for c in json.loads(r.stdout))


@pytest.mark.parametrize('url', ['https://example.invalid', 'redis://', 'redis://host:invalid', 'redis://host:0'])
def test_bad_redis_urls_fail_closed(url):
    assert redis_probe(url, allow=True).returncode != 0


def test_render_entrypoint_port_and_proxy_safety(monkeypatch):
    spec = importlib.util.spec_from_file_location('render_start', ROOT / 'deploy/render_start.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('PORT', '12345')
    monkeypatch.setenv('WEB_CONCURRENCY', '1')
    cmd = module.command()
    assert cmd[cmd.index('--port')+1] == '12345'
    assert '--no-proxy-headers' in cmd
    monkeypatch.setenv('PORT', '0')
    with pytest.raises(ValueError):
        module.command()
