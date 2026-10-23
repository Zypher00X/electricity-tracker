import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4, uuid5, NAMESPACE_URL
from fastapi import HTTPException
from app.electricity.service import ElectricityService, feature_redis, StorageUnavailable
from .repository import Repository, APPLIANCE_HEADERS, USAGE_HEADERS
from .schemas import UsageInput

logger=logging.getLogger(__name__)

def number(value):
    return None if value is None or value=='' else value

def view(row):
    data=dict(billing_month=row['billing_month'],appliance_name=row['appliance_name_snapshot'],category=row['category_snapshot'],category_custom=row.get('category_custom_snapshot') or None,
        quantity=int(row['quantity_snapshot']),brand=row.get('brand_snapshot',''),model=row.get('model_snapshot',''),rated_power_w=number(row['rated_power_w_snapshot']),average_power_w=number(row['average_power_w_snapshot']),
        hours_per_day=number(row['hours_per_day']),days_used=None if number(row['days_used']) is None else int(row['days_used']),monthly_kwh_per_unit=number(row['monthly_kwh_per_unit']),
        estimation_method=row['estimation_method'],source=row['energy_source'] if row['estimation_method']=='monthly_kwh' else row['power_source_snapshot'],notes=row['notes'])
    result=UsageInput.model_validate(data).model_dump(mode='json')
    result.update(id=row['usage_id'],appliance_id=row['appliance_id'],estimated_kwh=number(row['estimated_kwh']),status=row['status'],revision=int(row['revision']),created_at=row['created_at'],updated_at=row['updated_at'])
    return result

def estimated(data):
    if data.source=='unknown': return None
    if data.estimation_method=='monthly_kwh':
        result=None if data.monthly_kwh_per_unit is None else data.monthly_kwh_per_unit*data.quantity
    elif any(value is None for value in [data.average_power_w,data.hours_per_day,data.days_used]): return None
    else: result=data.average_power_w/Decimal(1000)*data.hours_per_day*data.days_used*data.quantity
    return None if result is None else str(result.quantize(Decimal('.0001'),rounding=ROUND_HALF_UP))

class Service(ElectricityService):
    def cached_data(self):
        raw=self.cache.get(self.cache_key)
        if raw is None: return None
        try: return json.loads(raw)
        except (ValueError,TypeError): self.cache.delete(self.cache_key);return None
    def store(self,data):
        self.cache.set(self.cache_key,json.dumps(data,default=str),ex=self.ttl)
    def list(self,user_id,month):
        try:
            data=self.cached_data()
            if data is None:
                with self.sheet_lock() as guard:
                    data=self.cached_data()
                    if data is None:
                        data=self.repository.load();guard();self.store(data)
            return [view(row) for row in data[1]['rows'] if row['user_id']==user_id and row['billing_month']==month and row['status']=='active']
        except Exception as error:
            logger.warning('Appliance read failed: %s',type(error).__name__)
            raise StorageUnavailable() from error
    def save(self,user_id,payload,request_id,usage_id=None,revision=None,cancel=False):
        try:
            with self.sheet_lock() as guard:
                data=self.repository.load();appliances,usage=data
                create_id=str(uuid5(NAMESPACE_URL,self.prefix+':'+user_id+':'+request_id))
                if usage_id is None and any(row['usage_id']==create_id and row['user_id']==user_id and row['request_id']!=request_id for row in usage['rows']):
                    raise HTTPException(409,'คำขอนี้บันทึกแล้วและรายการมีการเปลี่ยนแปลง กรุณาโหลดรายการใหม่')
                old=next((row for row in usage['rows'] if row['usage_id']==usage_id and row['user_id']==user_id),None) if usage_id else None
                if usage_id and old is None: raise HTTPException(404,'ไม่พบรายการ')
                replay=next((row for row in usage['rows'] if row['user_id']==user_id and row['request_id']==request_id),None)
                if replay:
                    if cancel and replay['status']!='cancelled': raise HTTPException(409,'รหัสคำขอถูกใช้กับการทำงานอื่นแล้ว')
                    if usage_id and replay['usage_id']!=usage_id: raise HTTPException(409,'รหัสคำขอถูกใช้แล้ว')
                    if not cancel and UsageInput.model_validate({k:v for k,v in view(replay).items() if k in UsageInput.model_fields}).model_dump()!=payload.model_dump():
                        raise HTTPException(409,'รหัสคำขอถูกใช้กับข้อมูลอื่นแล้ว')
                    return view(replay)
                if old and (int(old['revision'])!=revision or old['status']!='active'): raise HTTPException(409,'รายการเปลี่ยนแปลงแล้ว กรุณาโหลดใหม่')
                now=datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='microseconds')
                changes=[]
                if cancel:
                    row=dict(old,status='cancelled',revision=int(old['revision'])+1,updated_at=now,request_id=request_id)
                else:
                    appliance_id=old['appliance_id'] if old else str(uuid4())
                    row=dict(usage_id=usage_id or create_id,user_id=user_id,appliance_id=appliance_id,billing_month=payload.billing_month,
                        appliance_name_snapshot=payload.appliance_name,category_snapshot=payload.category,quantity_snapshot=payload.quantity,rated_power_w_snapshot=payload.rated_power_w,
                        average_power_w_snapshot=payload.average_power_w,power_source_snapshot=payload.source if payload.estimation_method=='average_power' else 'unknown',estimation_method=payload.estimation_method,
                        hours_per_day=payload.hours_per_day,days_used=payload.days_used,monthly_kwh_per_unit=payload.monthly_kwh_per_unit,energy_source=payload.source if payload.estimation_method=='monthly_kwh' else 'unknown',
                        estimated_kwh=estimated(payload),calculation_version='energy-v1',notes=payload.notes,created_at=old['created_at'] if old else now,updated_at=now,
                        category_custom_snapshot=payload.category_custom,brand_snapshot=payload.brand,model_snapshot=payload.model,status='active',revision=int(old['revision'])+1 if old else 1,request_id=request_id)
                    if old and payload.billing_month!=old['billing_month']: raise HTTPException(409,'ไม่สามารถย้ายเดือนของรายการเดิม')
                    if not old:
                        appliance=dict(appliance_id=appliance_id,user_id=user_id,appliance_name=payload.appliance_name,category=payload.category,brand=payload.brand,model=payload.model,quantity=payload.quantity,
                            rated_power_w=payload.rated_power_w,average_power_w=payload.average_power_w,power_source=row['power_source_snapshot'],estimation_method=payload.estimation_method,
                            default_hours_per_day=payload.hours_per_day,default_monthly_kwh_per_unit=payload.monthly_kwh_per_unit,status='active',notes=payload.notes,created_at=now,updated_at=now,category_custom=payload.category_custom)
                        changes.append((appliances,appliance,appliances['next'],APPLIANCE_HEADERS))
                target=old['_row'] if old else usage['next'];row['_row']=target
                changes.append((usage,row,target,USAGE_HEADERS))
                guard();self.cache.delete(self.cache_key);self.repository.commit(changes,guard)
                # Avoid a fresh Sheet read after confirmed commit; publish a coherent cache snapshot.
                for dataset,record,index,headers in changes:
                    dataset['rows']=[r for r in dataset['rows'] if r['_row']!=index]+[dict(record,_row=index)]
                    dataset['next']=max(dataset['next'],index+1)
                try: guard();self.store(data)
                except Exception: logger.warning('Appliance saved; cache refresh failed')
                return view(row)
        except HTTPException: raise
        except Exception as error:
            logger.warning('Appliance write failed: %s',type(error).__name__)
            raise StorageUnavailable() from error

repository=Repository()
namespace=hashlib.sha256((repository.spreadsheet_id+':'+':'.join(repository.names)).encode()).hexdigest()[:16]
service=Service(repository,feature_redis,'powertrack:appliances:'+namespace,ttl=30)
