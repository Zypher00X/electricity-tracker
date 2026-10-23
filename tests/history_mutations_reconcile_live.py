"""Inject a lost write acknowledgement only in a separate fixture process."""
import os
from decimal import Decimal
from uuid import uuid4
from app.electricity.service import service, StorageUnavailable
from app.history.mutations import mutate, EditInput
from app.services.auth_user_cache import load_users

assert os.environ.get('ELECTRICITY_TEST_MODE')=='live'
assert service.repository.sheet_name.startswith('test_')
records,_=service.repository.load();assert len(records)==1
record=records[0];user=next(u for u in load_users() if u['user_id']==record.user_id)
assert user['email'].startswith('advice-k6-') and user['email'].endswith('@example.com')
def payload(row,units):return EditInput(**{k:v for k,v in row.model_dump(mode='json').items() if k in ('billing_month','previous_meter','unit_price','service_charge')}|
    {'current_meter':units,'unit_price':'8.0000','service_charge':'50.00','expected_updated_at':row.updated_at,'request_id':str(uuid4())})
data=payload(record,120);original=service.repository.replace;writes=[]
def lost_ack(*args):
    original(*args);writes.append(1)
    raise TimeoutError('fixture lost acknowledgement after committed Sheets write')
service.repository.replace=lost_ack
try:mutate(service,record.user_id,record.record_id,data)
except StorageUnavailable:pass
else:raise AssertionError('Expected injected acknowledgement failure')
service.repository.replace=original
actual=next(r for r in service.repository.load()[0] if r.record_id==record.record_id)
assert actual.total_cost==1010 and actual.model_dump(mode='json')['total_cost']!='1010.00'
retried=mutate(service,record.user_id,record.record_id,data)
assert retried['replayed'] and len(writes)==1
assert service.cached()[0].total_cost==1010
# Restore the disposable browser fixture for visual evidence.
restored=mutate(service,record.user_id,record.record_id,payload(actual,100))
assert Decimal(restored['record']['total_cost'])==850
print('PASS: real Sheets normalized decimals, ambiguous write reconciled, one write only, Redis refreshed')
