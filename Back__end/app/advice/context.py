import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from app.analysis.service import AnalysisService, appliance_data


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def amount(value):
    return str(Decimal(value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def clean_name(value):
    return re.sub(r'[\x00-\x1f\x7f]', ' ', str(value))[:80]


class Context:
    def __init__(self, electricity, appliances, settings):
        self.electricity, self.appliances, self.settings = electricity, appliances, settings

    def get(self, owner, month=None):
        analysis = AnalysisService(self.electricity, self.appliances).get(owner, 12, month)
        month = analysis['end_month']
        bills = self.electricity.list_records(owner)
        bill = next((row for row in bills if row.billing_month == month), None)
        setting = self.settings.get(owner)
        usage = self.appliances.list(owner, month)
        datasets = appliance_data(self.appliances)
        own_masters = [row for row in datasets[0]['rows'] if row['user_id'] == owner]
        master_ids = {row['appliance_id'] for row in own_masters}
        usage = [row for row in usage if row['appliance_id'] in master_ids]
        # Hash only this owner's data; another account's writes do not invalidate answers.
        version = digest({'bills': [r.model_dump(mode='json') for r in bills],
            'masters': own_masters,
            'usage': usage, 'settings': setting.model_dump(mode='json') if setting else None})
        price = bill.unit_price if bill else setting.default_unit_price if setting else None
        budget = setting.monthly_budget if setting else None
        total = bill.total_cost if bill else None
        gap = max(Decimal(0), total - budget) if total is not None and budget is not None else None
        devices = []
        usage_by_id = {row['appliance_id']: row for row in usage}
        for row in analysis['appliances'][:20]:
            recorded = usage_by_id.get(row['appliance_id'], {})
            devices.append({key: row[key] for key in ('category', 'quantity', 'estimated_kwh', 'source', 'estimation_method')} |
                {'name': clean_name(row['name'])} |
                {key: recorded.get(key) for key in ('average_power_w', 'hours_per_day', 'days_used')})
        scenarios = []
        for row in usage:
            if len(scenarios) >= 3: break
            if row['category'] not in {'air_conditioner', 'computer', 'fan', 'lighting', 'television', 'game_console', 'monitor'}: continue
            if row['estimation_method'] != 'average_power' or row['source'] == 'unknown': continue
            values = [row.get(key) for key in ('average_power_w', 'hours_per_day', 'days_used')]
            if any(value is None or Decimal(str(value)) <= 0 for value in values): continue
            watts, hours, days = map(lambda n: Decimal(str(n)), values)
            reduction = (hours * Decimal('.1')).quantize(Decimal('.0001'))
            kwh = watts / 1000 * reduction * days * row['quantity']
            scenarios.append({'id': 'scenario-' + str(len(scenarios) + 1), 'name': clean_name(row['appliance_name']),
                'category': row['category'], 'time_reduction_percent': 10, 'hours_less_per_day': str(reduction),
                'days_used': int(days), 'quantity': row['quantity'], 'average_power_w': str(watts),
                'saved_kwh': amount(kwh), 'estimated_saved_baht': amount(kwh * price) if price is not None else None})
        missing = []
        if not bill: missing.append('ไม่มีบิลในเดือนที่เลือก')
        if not setting: missing.append('ยังไม่มีการตั้งค่าที่พักและงบ')
        if not devices: missing.append('ไม่มีรายการใช้เครื่องใช้ไฟฟ้าของเดือนที่เลือก')
        if analysis['appliance_summary']['unknown_items']: missing.append('บางเครื่องยังประเมินพลังงานไม่ได้')
        if len(analysis['appliances']) > 20: missing.append('แสดงเฉพาะเครื่องใช้ยี่สิบรายการแรกตามพลังงานประมาณการ')
        focus_latest = analysis['latest'] if analysis['latest'] and analysis['latest']['month'] == month else None
        facts = {'month': month, 'bill': focus_latest, 'household': {
            'residence_type': setting.residence_type if setting else 'unknown',
            'occupants': setting.occupants if setting else None},
            'budget': {'monthly_budget': str(budget) if budget is not None else None,
                'fixed_charge': str(bill.service_charge) if bill else None,
                'feasible_under_recorded_rate': budget >= bill.service_charge if budget is not None and bill else None,
                'gap_baht': amount(gap) if gap is not None else None,
                'reduction_percent': amount(gap / total * 100) if gap is not None and total else None,
                'target_kwh_reduction': amount(gap / price) if gap is not None and price else None,
                'unit_price': str(price) if price is not None else None,
                'price_source': 'selected_bill' if bill else 'settings_estimate' if price is not None else None},
            'devices': devices, 'device_totals': analysis['appliance_summary'], 'scenarios': scenarios,
            'missing_data': missing,
            'notes': ['เครื่องใช้เป็นค่าประมาณ อาจไม่ตรงกับมิเตอร์', 'สถานการณ์ลดเวลาเป็นสมมติฐาน ไม่ใช่ยอดประหยัดรับประกัน',
                'การเทียบมิเตอร์ต้องพิจารณาอากาศ จำนวนคน และกิจกรรมด้วย แม้จดในเวลาใกล้เคียงกัน',
                'ประมาณการเงินตามราคาต่อหน่วยที่บันทึก ยังไม่จำลองอัตราขั้นบันได ภาษี หรือการเปลี่ยนค่าบริการ']}
        return {'version': version, 'facts': facts, 'available_months': analysis['available_months']}
