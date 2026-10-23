"""Synthetic-only context shared by deterministic checks and live AI evaluation."""
import fakeredis
from decimal import Decimal
from demo_dataset import build_dataset
from advice_fixtures import Bills,Appliances
from app.electricity.service import ElectricityService
from app.electricity.schemas import ElectricityRecord
from app.appliances.service import Service
from app.settings.schemas import SettingsRecord
from app.advice.context import Context

class Settings:
    def get(self,owner):
        return SettingsRecord(user_id=owner,residence_type='house',occupants=3,monthly_budget='2000',default_unit_price='8',default_service_charge='50',
            created_at='2026-10-23T00:00:00+07:00',updated_at='2026-10-23T00:00:00+07:00')

def large_context(mismatch=False):
    owner='large-eval-owner';data=build_dataset(owner,'2026-05','2026-10-23T00:00:00+07:00')
    cache=fakeredis.FakeRedis(decode_responses=True);bills=Bills();bills.rows=[ElectricityRecord.model_validate(r) for r in data['bills']]
    if mismatch:
        original=bills.rows[-1];bills.rows[-1]=original.model_copy(update={'current_meter':original.previous_meter+100,'units_used':100,'energy_cost':Decimal(800),'total_cost':Decimal(850)})
    devices=Appliances()
    for ds,key in zip(devices.data,['masters','usage']):ds['rows']=[dict(r,_row=i) for i,r in enumerate(data[key],1)];ds['next']=25
    context=Context(ElectricityService(bills,cache,'eval:large:bills'),Service(devices,cache,'eval:large:devices'),Settings())
    return context,owner
