"""Explicitly isolated test server; never imported by the production entrypoint."""
import os
import threading

mode = os.getenv("ELECTRICITY_TEST_MODE")
if mode not in {"synthetic", "live"}:
    raise RuntimeError("Set ELECTRICITY_TEST_MODE only in an isolated test container")
if not os.getenv("GOOGLE_USERS_SHEET", "").startswith("test_"):
    raise RuntimeError("Test server must not use the real users worksheet")
if not os.getenv("GOOGLE_ELECTRICITY_SHEET", "").startswith("test_"):
    raise RuntimeError("Test server must not use the real electricity worksheet")

from app.main import app
from app.electricity import routes
from app.electricity.service import ElectricityService, feature_redis
from app.dependencies import auth as dependencies
from app.routes import auth as auth_routes
from app.services import auth_service


class FixtureRepository:
    def __init__(self):
        self.records, self.loads, self.writes = [], 0, 0
        self.mutex = threading.Lock()

    def load(self):
        with self.mutex:
            self.loads += 1
            return list(self.records), len(self.records) + 1

    def insert(self, record, next_row, guard):
        guard()
        with self.mutex:
            self.records.append(record)
            self.writes += 1

    def load_indexed(self):
        records, next_row = self.load()
        return records, {r.record_id:i for i,r in enumerate(records,1)}, next_row

    def replace(self, record, row, guard):
        guard()
        with self.mutex:
            self.records[row-1] = record
            self.writes += 1

    def remove(self, row, guard):
        guard()
        with self.mutex:
            self.records.pop(row-1)
            self.writes += 1


if mode == "synthetic":
    # Only the external Sheet repository is substituted; JWT, Redis session,
    # rate limiting, role dependencies, service and HTTP routes are the real code.
    repository = FixtureRepository()
    routes.service = ElectricityService(repository, feature_redis, "test:electricity:synthetic", ttl=30)
    users = {}
    find_email = lambda email: next((u for u in users.values() if u["email"] == email), None)
    find_phone = lambda phone: next((u for u in users.values() if u["phone"] == phone), None)
    dependencies.find_user_by_id = lambda user_id: users.get(user_id)
    auth_routes.find_user_by_identifier = lambda name: find_email(name) or find_phone(name)
    auth_service.find_user_by_email = find_email
    auth_service.find_user_by_phone = find_phone
    auth_service.create_user = lambda **data: users.update({data["user_id"]: data})
    auth_service.update_last_login_at = lambda **data: True


@app.get("/_test/info")
def test_info():
    result = {"mode": mode, "isolated": True}
    if mode == "synthetic":
        result.update(repository_loads=repository.loads, repository_writes=repository.writes,
                      records=len(repository.records))
    return result
