"""Read-only checks of the authorized account's actual seeded data, no chat calls."""
import json
from decimal import Decimal
from app.electricity.service import service as electricity
from app.appliances.service import service as appliances,estimated
from app.appliances.schemas import UsageInput
from app.settings.service import service as settings
from app.dashboard.service import dashboard
from app.history.service import history
from app.analysis.service import AnalysisService
from app.advice.context import Context
from app.advice.export_prompt import render_body
from demo_dataset import VERSION,MARKER

OWNER='dd3e76ab-6478-4fb5-b055-08217ae80534'
assert electricity.repository.sheet_name=='electricity_records'
assert appliances.repository.names==['appliances','appliance_usage_monthly']
bills=electricity.list_records(OWNER);assert len(bills)==29
pages=[history(electricity,OWNER,page=i) for i in range(1,6)]
assert pages[0]['total']==29 and pages[0]['total_pages']==5
ids=[r.record_id for p in pages for r in p['records']];assert len(ids)==len(set(ids))==29
monthly=appliances.list(OWNER,'2026-05');assert len(monthly)==24
known=[Decimal(str(r['estimated_kwh'])) for r in monthly if r['estimated_kwh'] is not None]
assert len(known)==22 and sum(known)==Decimal('247.55')
for row in monthly:
    data=UsageInput.model_validate({k:v for k,v in row.items() if k in UsageInput.model_fields})
    assert estimated(data)==row['estimated_kwh'] or (estimated(data) is not None and Decimal(estimated(data))==Decimal(str(row['estimated_kwh'])))
    assert MARKER==row['notes']
for months in (3,6,12):
    a=AnalysisService(electricity,appliances).get(OWNER,months,'2026-05')
    assert len(a['series'])==months and len(a['appliances'])==24
    assert Decimal(a['appliance_summary']['estimated_kwh'])==sum(known)
d=dashboard(electricity,OWNER,'2026-05');assert d['units_used']==285 and Decimal(d['total_cost'])==2330
assert len(d['series'])==6 and d['average_bill_count']==6
context=Context(electricity,appliances,settings).get(OWNER,'2026-05');f=context['facts']
assert f['device_totals']['items']==24 and f['device_totals']['estimated_items']==22 and f['device_totals']['unknown_items']==2
assert len(f['devices'])==20 and len(f['scenarios'])==3
assert Decimal(f['device_totals']['difference_kwh'])==Decimal('-37.45')
prompt=render_body(f)
assert '24' in prompt and '20' in prompt and '247.55' in prompt and '285' in prompt
# Other existing accounts must not inherit this owner's rows or appliance joins.
from app.services.auth_user_cache import auth_user_cache
for user in auth_user_cache.snapshot() or []:
    if user['role']=='user' and user['user_id']!=OWNER:
        own=electricity.list_records(user['user_id'])
        assert not set(ids).intersection(r.record_id for r in own)
        assert not set(r['id'] for r in monthly).intersection(r['id'] for r in appliances.list(user['user_id'],'2026-05'))
print(json.dumps({'passed':True,'bill_count':len(bills),'history_pages':5,'device_count':24,'estimated_items':22,
    'unknown_items':2,'estimated_kwh':str(sum(known)),'meter_kwh':285,'selected_total':d['total_cost'],
    'ai_device_details':20,'ai_total_items':24,'ai_scenarios':3,'prompt_export_checked':True}))
