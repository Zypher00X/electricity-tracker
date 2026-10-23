"""Synthetic account data built through the actual calculation services."""
import copy
from uuid import uuid4
import fakeredis
from app.advice.context import Context
from app.electricity.service import ElectricityService
from app.electricity.schemas import ElectricityCreate
from app.appliances.service import Service
from app.appliances.schemas import UsageInput
from app.settings.schemas import SettingsRecord


class Bills:
    def __init__(self): self.rows = []
    def load(self): return self.rows[:], len(self.rows) + 1
    def insert(self, record, row, guard): guard(); self.rows.append(record)


class Appliances:
    def __init__(self): self.data = [{'rows': [], 'next': 1}, {'rows': [], 'next': 1}]
    def load(self): return copy.deepcopy(self.data)
    def commit(self, changes, guard):
        guard()
        for _, record, index, headers in changes:
            target = self.data[0 if 'appliance_name' in record else 1]
            target['rows'] = [r for r in target['rows'] if r['_row'] != index] + [dict(record, _row=index)]
            target['next'] = max(target['next'], index + 1)


class Settings:
    def get(self, owner):
        if owner != 'fixture-owner': return None
        return SettingsRecord(user_id=owner, residence_type='apartment', occupants=2, default_unit_price='8',
            monthly_budget='1400', created_at='2026-10-01T00:00:00+07:00', updated_at='2026-10-01T00:00:00+07:00')


def fixture_context():
    cache = fakeredis.FakeRedis(decode_responses=True)
    electricity = ElectricityService(Bills(), cache, 'eval:electricity')
    appliances = Service(Appliances(), cache, 'eval:appliances')
    electricity.create('fixture-owner', ElectricityCreate(billing_month='2026-10', previous_meter=0, current_meter=200, unit_price='8', service_charge='0'))
    electricity.create('fixture-owner', ElectricityCreate(billing_month='2026-09', previous_meter=0, current_meter=180, unit_price='8', service_charge='0'))
    for data in [dict(appliance_name='แอร์ห้องนอน', category='air_conditioner', quantity=1, average_power_w='500', hours_per_day='8', days_used=30, source='user_estimate'),
        dict(appliance_name='คอมพิวเตอร์', category='computer', quantity=1, average_power_w='125', hours_per_day='8', days_used=25, source='measured'),
        dict(appliance_name='ตู้เย็น', category='refrigerator', quantity=1, monthly_kwh_per_unit='30', estimation_method='monthly_kwh', source='energy_label'),
        dict(appliance_name='เครื่องใช้ที่ไม่ทราบกำลังไฟ', category='other', category_custom='เครื่องใช้ส่วนตัว', source='unknown')]:
        appliances.save('fixture-owner', UsageInput(billing_month='2026-10', **data), str(uuid4()))
    return Context(electricity, appliances, Settings())
