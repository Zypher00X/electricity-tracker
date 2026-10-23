"""Synthetic-only full-stack load fixture: 20 populated owners + one empty owner."""
import json
from decimal import Decimal
from uuid import uuid5,NAMESPACE_URL
from reports_runtime import app,mode
from runtime_app import users
from app.electricity import routes as electricity
from app.appliances import routes as appliances
from app.settings import routes as settings
from app.electricity.schemas import ElectricityRecord
from app.settings.schemas import SettingsRecord
from app.utils.security import hash_password
from demo_dataset import build_dataset

if mode!='synthetic':raise RuntimeError('Synthetic-only fixture server')
accounts=[]
@app.post('/_test/large-seed')
def seed():
    if accounts:return {'isolated':True,'accounts':accounts,'populated':20,'empty':1}
    password_hash=hash_password('LargeFixturePassword123!')
    er,ar,sr=electricity.service.repository,appliances.service.repository,settings.service.repository
    for i in range(21):
        owner=str(uuid5(NAMESPACE_URL,'powertrack-large-owner-'+str(i)))
        email=f'large-fixture-{i}@example.com'
        users[owner]=dict(user_id=owner,full_name='Large Fixture '+str(i),email=email,phone='0890000'+str(i).zfill(3),
            role='user',status='active',password_hash=password_hash)
        account={'id':owner,'email':email,'index':i,'populated':i<20,'usage_ids':[]}
        if i<20:
            data=build_dataset(owner,'2026-05','2026-10-23T00:00:00+07:00')
            for raw in data['bills']:
                row=ElectricityRecord.model_validate(raw);units=row.units_used+i
                row=row.model_copy(update={'current_meter':row.previous_meter+units,'units_used':units,
                    'energy_cost':Decimal(units)*row.unit_price,'total_cost':Decimal(units)*row.unit_price+row.service_charge})
                er.records.append(row)
            for dataset,key in zip(ar.data,['masters','usage']):
                for raw in data[key]:
                    row=json.loads(json.dumps(raw,default=str));row['_row']=dataset['next'];dataset['next']+=1;dataset['rows'].append(row)
            account['usage_ids']=[r['usage_id'] for r in data['usage']]
            sr.rows.append((len(sr.rows)+1,SettingsRecord(user_id=owner,residence_type='house',occupants=3,default_unit_price='8',default_service_charge='50',
                monthly_budget=str(2000+10*i),created_at='2026-10-23T00:00:00+07:00',updated_at='2026-10-23T00:00:00+07:00')))
        accounts.append(account)
    electricity.service.cache.delete(electricity.service.cache_key,appliances.service.cache_key,settings.service.cache_key)
    return {'isolated':True,'accounts':accounts,'populated':20,'empty':1}

@app.get('/_test/large-stats')
def stats():
    from advice_runtime import provider
    from app.reports import routes as reports
    return {'isolated':True,'accounts':len(accounts),'bills':len(electricity.service.repository.records),
        'masters':len(appliances.service.repository.data[0]['rows']),'usage':len(appliances.service.repository.data[1]['rows']),
        'bill_reads':electricity.service.repository.loads,'appliance_reads':appliances.service.repository.loads,
        'settings_reads':settings.service.repository.loads,'report_reads':reports.service.repository.loads,
        'report_writes':reports.service.repository.writes,'provider_calls':provider.calls}
