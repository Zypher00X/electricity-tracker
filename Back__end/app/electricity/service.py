import hashlib
import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from gspread.exceptions import APIError
from redis.exceptions import RedisError, LockError

from app.core.redis import create_redis_client
from .repository import SheetRepository
from .schemas import ElectricityRecord

logger = logging.getLogger(__name__)


class DuplicateMonth(Exception):
    pass


class StorageUnavailable(Exception):
    pass


class ElectricityService:
    def __init__(self, repository, cache, prefix, ttl=30):
        self.repository, self.cache, self.prefix, self.ttl = repository, cache, prefix, ttl
        self.cache_key = prefix + ":records:v1"

    @contextmanager
    def sheet_lock(self):
        # One writer per sheet also coordinates cache fills with writes.
        lock = self.cache.lock(self.prefix + ":io-lock", timeout=120,
                               blocking_timeout=5, thread_local=False)
        if not lock.acquire():
            raise StorageUnavailable("Sheet is busy")
        stop, lost = threading.Event(), threading.Event()

        def renew():
            while not stop.wait(20):
                try:
                    lock.extend(120, replace_ttl=True)
                except RedisError:
                    lost.set()
                    return

        thread = threading.Thread(target=renew, daemon=True)
        thread.start()

        def guard():
            if lost.is_set() or not lock.owned():
                raise StorageUnavailable("Write lock lost")

        try:
            yield guard
        finally:
            stop.set()
            thread.join(timeout=6)
            try:
                lock.release()  # token-safe Lua release
            except (RedisError, LockError):
                logger.warning("Electricity lock release failed; lease will expire")

    def cached(self):
        raw = self.cache.get(self.cache_key)
        if raw is None:
            return None
        try:
            return [ElectricityRecord.model_validate(v) for v in json.loads(raw)]
        except (ValueError, TypeError):
            self.cache.delete(self.cache_key)
            return None

    def cache_records(self, records):
        self.cache.setex(self.cache_key, self.ttl,
                        json.dumps([r.model_dump(mode="json") for r in records]))

    def source_call(self, operation):
        if self.cache.exists(self.prefix + ':source-cooldown'):
            raise StorageUnavailable('Source temporarily rate limited')
        try: return operation()
        except APIError as error:
            if error.code == 429:
                self.cache.set(self.prefix + ':source-cooldown', '1', ex=10)
            raise

    def list_records(self, user_id):
        try:
            records = self.cached()
            if records is None:
                with self.sheet_lock() as guard:
                    records = self.cached()
                    if records is None:
                        records, _ = self.source_call(self.repository.load)
                        guard()
                        self.cache_records(records)
            return sorted((r for r in records if r.user_id == user_id),
                          key=lambda r: r.billing_month, reverse=True)
        except StorageUnavailable:
            raise
        except Exception as error:
            logger.warning("Electricity read unavailable: %s", type(error).__name__)
            raise StorageUnavailable() from error

    def create(self, user_id, data):
        def exists(records):
            return any(r.user_id == user_id and r.billing_month == data.billing_month for r in records)

        try:
            cached = self.cached()
            if cached is not None and exists(cached):
                raise DuplicateMonth()
            with self.sheet_lock() as guard:
                cached = self.cached()
                if cached is not None and exists(cached):
                    raise DuplicateMonth()
                # Fresh source check for every new write; cache alone cannot
                # protect uniqueness against an externally inserted sheet row.
                records, next_row = self.source_call(self.repository.load)
                if exists(records):
                    guard()
                    self.cache_records(records)
                    raise DuplicateMonth()
                now = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")
                units = data.current_meter - data.previous_meter
                energy = (Decimal(units) * data.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                total = (energy + data.service_charge).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                record = ElectricityRecord(**data.model_dump(), record_id=str(uuid4()), user_id=user_id,
                    units_used=units, energy_cost=energy, total_cost=total, created_at=now, updated_at=now)
                guard()
                self.cache.delete(self.cache_key)  # cold readers take the same lock
                self.repository.insert(record, next_row, guard)
                # Once Sheets confirms success, cache failures must not turn a
                # committed write into an apparent failed save.
                try:
                    guard()
                    self.cache_records(records + [record])
                except (RedisError, StorageUnavailable):
                    logger.warning("Electricity saved, but cache refresh failed")
                return record
        except (DuplicateMonth, StorageUnavailable):
            raise
        except Exception as error:
            logger.warning("Electricity write unavailable: %s", type(error).__name__)
            raise StorageUnavailable() from error


repository = SheetRepository()
feature_redis = create_redis_client(timeout=3, max_connections=64)
namespace = hashlib.sha256((repository.spreadsheet_id + ":" + repository.sheet_name).encode()).hexdigest()[:16]
service = ElectricityService(repository, feature_redis, "powertrack:electricity:" + namespace,
                             ttl=max(1, min(int(os.getenv("ELECTRICITY_CACHE_SECONDS", "30")), 300)))
