"""Dashboard arithmetic over the existing shared electricity snapshot; no model I/O."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from app.analysis.service import percentage


def dashboard(storage, owner, month=None):
    bills = [r for r in storage.list_records(owner) if r.user_id == owner]
    by_month = {r.billing_month:r for r in bills}
    if len(by_month) != len(bills): raise ValueError('Duplicate owner/month')
    available = sorted(by_month, reverse=True)
    current_month = datetime.now(timezone(timedelta(hours=7))).strftime('%Y-%m')
    selected = month or (available[0] if available else current_month)
    year, number = map(int, selected.split('-'))
    index = (year-1)*12 + number-1
    calendar = [f'{i//12+1:04d}-{i%12+1:02d}' for i in range(max(0,index-5),index+1)]
    previous_month = f'{(index-1)//12+1:04d}-{(index-1)%12+1:02d}' if index else None
    bill, previous = by_month.get(selected), by_month.get(previous_month)
    known = [by_month[m] for m in calendar if m in by_month]
    average = sum((b.total_cost for b in known), Decimal(0))/len(known) if known else None
    total = bill.total_cost if bill else None
    breakdown = []
    if bill:
        breakdown = [{'key':key,'amount':str(value),'percent':None}
                     for key,value in [('energy_cost',bill.energy_cost),('service_charge',bill.service_charge)]]
        for part in breakdown:
            part['percent'] = str((Decimal(part['amount'])/total*100).quantize(Decimal('.1'),rounding=ROUND_HALF_UP)) if total else None
    return {'month':selected,'current_month':current_month,'available_months':available,'has_bill':bill is not None,
        'previous_month':previous_month,'units_used':bill.units_used if bill else None,
        'total_cost':str(total) if total is not None else None,
        'units_change_percent':percentage(Decimal(bill.units_used),Decimal(previous.units_used)) if bill and previous else None,
        'cost_change_percent':percentage(total,previous.total_cost) if bill and previous else None,
        'average_cost':str(average.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)) if average is not None else None,
        'average_bill_count':len(known),'period_start':calendar[0],'period_end':selected,
        'versus_average_percent':percentage(total,average),
        'series':[{'month':m,'total_cost':str(by_month[m].total_cost) if m in by_month else None} for m in calendar],
        'cost_breakdown':breakdown}
