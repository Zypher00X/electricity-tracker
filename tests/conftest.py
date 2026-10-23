import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Back__end"))
for key, value in {"JWT_SECRET_KEY": "test-only-secret-" * 8, "REDIS_PASSWORD": "test-password",
    "GOOGLE_OAUTH_CLIENT_ID": "test-client", "GOOGLE_OAUTH_CLIENT_SECRET": "test-secret",
    "GOOGLE_SPREADSHEET_ID": "test-only-spreadsheet"}.items():
    os.environ[key] = value

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import auth as dependencies
from app.electricity import routes
from app.electricity.service import ElectricityService
from app.routes import auth as auth_routes
from app.history import routes as history_routes
from app.services import session_service, rate_limit_service, auth_service
from app.utils.security import hash_password


class MemoryRecords:
    def __init__(self):
        self.records, self.loads, self.writes = [], 0, 0
        self.fail_before = False
        self.fail_after = False

    def load(self):
        self.loads += 1
        return list(self.records), len(self.records) + 1

    def insert(self, record, next_row, guard):
        guard()
        if self.fail_before:
            raise TimeoutError("before commit")
        self.writes += 1
        self.records.append(record)
        if self.fail_after:
            raise TimeoutError("ambiguous commit")

    def load_indexed(self):
        records, next_row = self.load()
        return records, {r.record_id:i for i,r in enumerate(records,1)}, next_row

    def replace(self, record, row, guard):
        guard()
        if self.fail_before: raise TimeoutError('before update')
        self.records[row-1] = record; self.writes += 1
        if self.fail_after: raise TimeoutError('ambiguous update')

    def remove(self, row, guard):
        guard()
        if self.fail_before: raise TimeoutError('before delete')
        self.records.pop(row-1); self.writes += 1
        if self.fail_after: raise TimeoutError('ambiguous delete')


@pytest.fixture(scope="session")
def password_hash():
    return hash_password("FixturePassword123!")


@pytest.fixture
def system(monkeypatch, password_hash):
    cache = fakeredis.FakeRedis(decode_responses=True)
    repository = MemoryRecords()
    service = ElectricityService(repository, cache, "test:electricity", ttl=30)
    monkeypatch.setattr(routes, "service", service)
    monkeypatch.setattr(session_service, "redis_client", cache)
    monkeypatch.setattr(rate_limit_service, "redis_client", cache)
    users = {name: dict(user_id=name, full_name="Fixture User", email=name+"@example.com",
        phone={"user-a":"0812345678", "user-b":"0822345678", "admin":"0832345678"}[name],
        role="admin" if name == "admin" else "user", status="active", password_hash=password_hash)
        for name in ["user-a", "user-b", "admin"]}
    find_id = lambda user_id: users.get(user_id)
    find_email = lambda email: next((u for u in users.values() if u["email"] == email), None)
    find_phone = lambda phone: next((u for u in users.values() if u["phone"] == phone), None)
    monkeypatch.setattr(dependencies, "find_user_by_id", find_id)
    monkeypatch.setattr(auth_routes, "find_user_by_identifier", lambda name: find_email(name) or find_phone(name))
    monkeypatch.setattr(auth_service, "find_user_by_email", find_email)
    monkeypatch.setattr(auth_service, "find_user_by_phone", find_phone)
    monkeypatch.setattr(auth_service, "update_last_login_at", lambda **kwargs: True)
    monkeypatch.setattr(auth_service, "create_user", lambda **kwargs: users.update({kwargs["user_id"]: kwargs}))
    app = FastAPI()
    app.include_router(auth_routes.router)
    app.include_router(routes.router)
    app.include_router(history_routes.router)
    client = TestClient(app)
    return client, service, repository, cache, users


def login(client, name="user-a"):
    response = client.post("/api/auth/login", json={"identifier": name+"@example.com", "password": "FixturePassword123!"})
    assert response.status_code == 200, response.text
    return response
