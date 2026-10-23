"""Owner-scoped bill mutations using the existing electricity cache and lock."""
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.electricity.schemas import ElectricityCreate, ElectricityRecord
from app.electricity.service import StorageUnavailable

logger = logging.getLogger(__name__)


class Identity(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_updated_at: str = Field(min_length=1, max_length=80)
    request_id: UUID


class EditInput(ElectricityCreate, Identity):
    pass


LIMIT = '''
local t=redis.call('TIME');local now=tonumber(t[1])+tonumber(t[2])/1000000
redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',now-60)
if redis.call('ZCARD',KEYS[1])>=10 then return 0 end
redis.call('ZADD',KEYS[1],now,ARGV[1]);redis.call('EXPIRE',KEYS[1],61);return 1
'''


def mutate(storage, owner, record_id, data, deleting=False):
    identity = storage.prefix + ':mutations:' + hashlib.sha256(owner.encode()).hexdigest()[:24]
    key = identity + ':request:' + str(data.request_id)
    serialized = json.dumps({'id': record_id, 'delete': deleting, 'data': data.model_dump(mode='json')}, sort_keys=True)
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    try:
        # Completed receipts and obvious owner/version failures need no sheet lock
        # or source I/O. All new writes still recheck under the shared lock below.
        receipt = json.loads(storage.cache.get(key) or 'null')
        if receipt:
            if receipt['fingerprint'] != fingerprint:
                raise HTTPException(409, 'รหัสคำขอนี้ถูกใช้กับข้อมูลอื่นแล้ว')
            if receipt['status'] == 'done': return receipt['response'] | {'replayed': True}
        else:
            cached = storage.cached()
            if cached is not None:
                known = next((r for r in cached if r.record_id == record_id and r.user_id == owner), None)
                if known is None: raise HTTPException(404, 'ไม่พบรายการค่าไฟนี้')
                if known.updated_at != data.expected_updated_at:
                    raise HTTPException(409, 'รายการถูกเปลี่ยนแปลงแล้ว กรุณาโหลดข้อมูลล่าสุดก่อนแก้ไขหรือลบ')
        with storage.sheet_lock() as guard:
            saved = json.loads(storage.cache.get(key) or 'null')
            if saved and saved['fingerprint'] != fingerprint:
                raise HTTPException(409, 'รหัสคำขอนี้ถูกใช้กับข้อมูลอื่นแล้ว')
            if saved and saved['status'] == 'done': return saved['response'] | {'replayed': True}
            if not saved:
                cached = storage.cached()
                if cached is not None:
                    known = next((r for r in cached if r.record_id == record_id and r.user_id == owner), None)
                    if known is None: raise HTTPException(404, 'ไม่พบรายการค่าไฟนี้')
                    if known.updated_at != data.expected_updated_at:
                        raise HTTPException(409, 'รายการถูกเปลี่ยนแปลงแล้ว กรุณาโหลดข้อมูลล่าสุดก่อนแก้ไขหรือลบ')
                if not storage.cache.eval(LIMIT, 1, identity+':rate', str(data.request_id)):
                    raise HTTPException(429, 'แก้ไขหรือลบได้สิบครั้งต่อนาที กรุณารอสักครู่', headers={'Retry-After':'60'})
            records, positions, _ = storage.source_call(storage.repository.load_indexed)
            old = next((r for r in records if r.record_id == record_id and r.user_id == owner), None)
            if saved and saved['status'] == 'pending':
                target = saved['target']
                # Sheets normalizes numeric cells (e.g. 850.00 -> 850).
                # Compare typed Decimal values, not their serialized spelling.
                if (deleting and old is None) or (not deleting and old and old == ElectricityRecord.model_validate(target)):
                    response = {'message': 'ลบข้อมูลค่าไฟสำเร็จ' if deleting else 'แก้ไขข้อมูลค่าไฟสำเร็จ',
                                'record_id': record_id, 'record': target, 'replayed': True}
                    guard(); storage.cache_records(records)
                    storage.cache.set(key, json.dumps({'fingerprint': fingerprint, 'status': 'done', 'response': response}), ex=3600)
                    return response
            if old is None:
                guard(); storage.cache_records(records)
                raise HTTPException(404, 'ไม่พบรายการค่าไฟนี้')
            if old.updated_at != data.expected_updated_at:
                guard(); storage.cache_records(records)
                raise HTTPException(409, 'รายการถูกเปลี่ยนแปลงแล้ว กรุณาโหลดข้อมูลล่าสุดก่อนแก้ไขหรือลบ')
            target = None
            if not deleting:
                if any(r.user_id == owner and r.billing_month == data.billing_month and r.record_id != record_id for r in records):
                    raise HTTPException(409, 'มีข้อมูลค่าไฟของเดือนนี้แล้ว กรุณาเลือกเดือนอื่น')
                if saved:
                    target = saved['target']
                else:
                    now = datetime.now(timezone.utc)
                    previous = datetime.fromisoformat(old.updated_at)
                    if now <= previous: now = previous + timedelta(microseconds=1)
                    units = data.current_meter - data.previous_meter
                    energy = (Decimal(units)*data.unit_price).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                    values = data.model_dump(exclude={'expected_updated_at','request_id'})
                    target = ElectricityRecord(**values, record_id=old.record_id, user_id=owner, units_used=units,
                        energy_cost=energy, total_cost=(energy+data.service_charge).quantize(Decimal('.01'), rounding=ROUND_HALF_UP),
                        created_at=old.created_at, updated_at=now.isoformat(timespec='microseconds')).model_dump(mode='json')
            storage.cache.set(key, json.dumps({'fingerprint':fingerprint, 'status':'pending', 'target':target}), ex=3600)
            guard(); storage.cache.delete(storage.cache_key)
            if deleting: storage.source_call(lambda: storage.repository.remove(positions[record_id], guard))
            else: storage.source_call(lambda: storage.repository.replace(ElectricityRecord.model_validate(target), positions[record_id], guard))
            changed = [r for r in records if r.record_id != record_id]
            if target: changed.append(ElectricityRecord.model_validate(target))
            response = {'message':'ลบข้อมูลค่าไฟสำเร็จ' if deleting else 'แก้ไขข้อมูลค่าไฟสำเร็จ',
                        'record_id':record_id, 'record':target, 'replayed':False}
            try:
                guard(); storage.cache_records(changed)
                storage.cache.set(key, json.dumps({'fingerprint':fingerprint,'status':'done','response':response}), ex=3600)
            except Exception: logger.warning('Electricity mutation committed; cache refresh unavailable')
            return response
    except (HTTPException, StorageUnavailable): raise
    except Exception as error:
        logger.warning('Electricity mutation unavailable: %s', type(error).__name__)
        raise StorageUnavailable() from error
