from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError

from conftest import login
from app.electricity.schemas import ElectricityCreate
from app.electricity.service import DuplicateMonth, StorageUnavailable
from app.electricity.repository import HEADERS, SheetRepository

PAYLOAD = {"billing_month": "2026-10", "previous_meter": 12456, "current_meter": 12780,
           "unit_price": "3.2484", "service_charge": "38.22"}


def test_save_decimal_read_and_duplicate(system):
    client, service, repo, cache, _ = system
    login(client)
    response = client.post("/api/electricity", json=PAYLOAD)
    assert response.status_code == 201
    record = response.json()["record"]
    assert record["user_id"] == "user-a"
    assert record["units_used"] == 324
    assert Decimal(record["energy_cost"]) == Decimal("1052.48")
    assert Decimal(record["total_cost"]) == Decimal("1090.70")
    assert client.get("/api/electricity").json()["records"] == [record]
    loads = repo.loads
    assert client.post("/api/electricity", json=PAYLOAD).status_code == 409
    assert repo.loads == loads and repo.writes == 1
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("changes", [
    {"billing_month":"2026-13"}, {"billing_month":"2026-1"}, {"billing_month":"0000-01"},
    {"previous_meter":-1}, {"current_meter":100}, {"previous_meter":1.5},
    {"current_meter":True}, {"unit_price":0}, {"unit_price":"NaN"}, {"unit_price":"Infinity"},
    {"unit_price":"1.12345"}, {"service_charge":-1}, {"service_charge":"2.001"},
    {"user_id":"other"}, {"total_cost":"0"}, {"units_used":0}, {"role":"admin"}
])
def test_validation_and_tampering(system, changes):
    client, _, repo, _, _ = system
    login(client)
    assert client.post("/api/electricity", json=PAYLOAD | changes).status_code == 422
    assert repo.writes == 0


def test_owner_isolation_and_same_month_other_user(system):
    client, _, _, _, _ = system
    login(client)
    a = client.post("/api/electricity", json=PAYLOAD).json()["record"]
    login(client, "user-b")
    assert client.get("/api/electricity").json()["records"] == []
    b = client.post("/api/electricity", json=PAYLOAD).json()["record"]
    assert b["record_id"] != a["record_id"]
    assert [r["user_id"] for r in client.get("/api/electricity").json()["records"]] == ["user-b"]


def test_auth_rbac_revocation_unchanged(system):
    client, _, repo, _, users = system
    assert client.get("/api/electricity").status_code == 401
    assert client.post("/api/electricity", json=PAYLOAD).status_code == 401
    login(client, "admin")
    assert client.post("/api/electricity", json=PAYLOAD).status_code == 403
    login(client)
    assert client.get("/api/auth/me").status_code == 200
    users["user-a"]["role"] = "admin"
    assert client.get("/api/electricity").status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert repo.writes == 0


def test_logout_and_register_regression(system):
    client, _, _, _, _ = system
    login(client)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    payload = {"full_name":"New User", "email":"new@example.com", "phone":"0842345678", "password":"NewPassword123!"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409
    assert client.post("/api/auth/login", json={"identifier":"new@example.com", "password":"NewPassword123!"}).status_code == 200


def test_origin_and_content_type(system):
    client, _, repo, _, _ = system
    login(client)
    assert client.post("/api/electricity", json=PAYLOAD, headers={"Origin":"https://attacker.invalid"}).status_code == 403
    assert client.post("/api/electricity", json=PAYLOAD, headers={"Sec-Fetch-Site":"cross-site"}).status_code == 403
    assert client.post("/api/electricity", content="{}", headers={"Content-Type":"text/plain"}).status_code == 415
    assert client.post("/api/electricity", json=PAYLOAD, headers={"Origin":"http://testserver"}).status_code == 201
    assert repo.writes == 1


def test_parallel_same_month_single_write(system):
    _, service, repo, _, _ = system
    def save(_):
        try:
            service.create("user-a", ElectricityCreate(**PAYLOAD))
            return 201
        except DuplicateMonth:
            return 409
    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(save, range(40)))
    assert statuses.count(201) == 1 and statuses.count(409) == 39
    assert repo.writes == 1


def test_cache_single_flight_and_expiry(system):
    _, service, repo, cache, _ = system
    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda _: service.list_records("user-a"), range(40)))
    assert repo.loads == 1
    assert 0 < cache.ttl(service.cache_key) <= 30
    cache.delete(service.cache_key)
    service.list_records("user-a")
    assert repo.loads == 2


def test_ambiguous_write_reconciles_without_duplicate(system):
    _, service, repo, _, _ = system
    repo.fail_after = True
    with pytest.raises(StorageUnavailable):
        service.create("user-a", ElectricityCreate(**PAYLOAD))
    repo.fail_after = False
    with pytest.raises(DuplicateMonth):
        service.create("user-a", ElectricityCreate(**PAYLOAD))
    assert repo.writes == 1


def test_failure_before_write_leaves_no_record(system):
    _, service, repo, _, _ = system
    repo.fail_before = True
    with pytest.raises(StorageUnavailable):
        service.create("user-a", ElectricityCreate(**PAYLOAD))
    assert repo.records == []
    repo.fail_before = False
    assert service.create("user-a", ElectricityCreate(**PAYLOAD)).units_used == 324


def test_cache_failure_after_commit_is_success(system, monkeypatch):
    _, service, repo, cache, _ = system
    monkeypatch.setattr(cache, "setex", Mock(side_effect=ConnectionError()))
    assert service.create("user-a", ElectricityCreate(**PAYLOAD)).user_id == "user-a"
    assert repo.writes == 1


def test_redis_unavailable_fails_closed(system, monkeypatch):
    _, service, repo, cache, _ = system
    monkeypatch.setattr(cache, "get", Mock(side_effect=ConnectionError()))
    with pytest.raises(StorageUnavailable):
        service.create("user-a", ElectricityCreate(**PAYLOAD))
    assert repo.writes == 0


def test_round_half_up_and_zero_usage(system):
    _, service, _, _, _ = system
    record = service.create("user-a", ElectricityCreate(**(PAYLOAD | {"previous_meter":0, "current_meter":1, "unit_price":"0.005", "service_charge":"0"})))
    assert record.total_cost == Decimal("0.01")
    zero = service.create("user-a", ElectricityCreate(**(PAYLOAD | {"billing_month":"2026-11", "previous_meter":5, "current_meter":5})))
    assert zero.units_used == 0 and zero.total_cost == Decimal("38.22")


def test_repository_atomic_native_table_request(system, monkeypatch):
    _, service, _, _, _ = system
    record = service.create("user-a", ElectricityCreate(**PAYLOAD))
    repository = SheetRepository()
    client = Mock()
    client.spreadsheets_get.return_value = {"sheets":[{"properties":{"sheetId":10701,"gridProperties":{"rowCount":1000}}}]}
    repository.local.sheet_id, repository.local.table_id = 10701, "table-1"
    monkeypatch.setattr(repository, "connection", lambda: client)
    guard = Mock()
    repository.insert(record, 1, guard)
    requests = client.batch_update.call_args.args[1]["requests"]
    assert requests[0]["updateCells"]["range"]["endColumnIndex"] == len(HEADERS)
    assert requests[1]["updateTable"]["table"]["range"]["endRowIndex"] == 2
    guard.assert_called_once()
