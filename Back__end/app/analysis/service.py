from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from app.appliances.service import view, estimated
from app.appliances.schemas import UsageInput
from app.electricity.service import StorageUnavailable


def shift(month, offset):
    year, number = map(int, month.split('-'))
    index = year*12 + number-1 + offset
    year, number = divmod(index,12)
    if not 1 <= year <= 9999: raise ValueError('Month range outside supported years')
    return f'{year:04d}-{number+1:02d}'


def percentage(current, previous):
    if current is None or previous is None or previous == 0: return None
    return str(((current-previous)/previous*100).quantize(Decimal('.1'),rounding=ROUND_HALF_UP))


def appliance_data(storage):
    data=storage.cached_data()
    if data is None:
        with storage.sheet_lock() as guard:
            data=storage.cached_data()
            if data is None:
                data=storage.repository.load();guard();storage.store(data)
    return data


def analyze(user_id, bills, datasets, months=12, end_month=None):
    # Enforce ownership before joins, dates, aggregates or metadata.
    bills=[row for row in bills if row.user_id==user_id]
    masters={row['appliance_id']:row for row in datasets[0]['rows'] if row['user_id']==user_id}
    usage=[row for row in datasets[1]['rows'] if row['user_id']==user_id and row['status']=='active' and row['appliance_id'] in masters]
    available=sorted({row.billing_month for row in bills}|{row['billing_month'] for row in usage})
    if end_month is None:
        end_month=available[-1] if available else datetime.now(timezone(timedelta(hours=7))).strftime('%Y-%m')
    calendar=[shift(end_month,index) for index in range(1-months,1)]
    by_month={row.billing_month:row for row in bills}
    if len(by_month)!=len(bills):raise ValueError('Duplicate owner billing month')
    selected=[by_month[month] for month in calendar if month in by_month]
    latest=selected[-1] if selected else None
    previous_month=None
    if latest:
        try: previous_month=shift(latest.billing_month,-1)
        except ValueError: pass
    previous=by_month.get(previous_month)
    latest_view=None
    if latest:
        latest_view=dict(month=latest.billing_month,total_cost=str(latest.total_cost),units_used=latest.units_used,
            energy_cost=str(latest.energy_cost),service_charge=str(latest.service_charge),
            cost_change_percent=percentage(latest.total_cost,previous.total_cost if previous else None),
            units_change_percent=percentage(Decimal(latest.units_used),Decimal(previous.units_used) if previous else None),
            previous_month=previous_month,previous_total_cost=str(previous.total_cost) if previous else None)
    def extreme(high):
        if not selected:return None
        row=(max if high else min)(selected,key=lambda row:(row.units_used,row.billing_month))
        return dict(month=row.billing_month,units_used=row.units_used)
    series=[]
    for month in calendar:
        bill=by_month.get(month)
        series.append(dict(month=month,units_used=bill.units_used if bill else None,total_cost=str(bill.total_cost) if bill else None))
    focus_month=end_month
    appliance_rows=[];seen=set()
    for row in usage:
        if row['billing_month']!=focus_month:continue
        if row['appliance_id'] in seen:raise ValueError('Duplicate appliance/month')
        seen.add(row['appliance_id'])
        snapshot=view(row)
        payload=UsageInput.model_validate({key:value for key,value in snapshot.items() if key in UsageInput.model_fields})
        kwh=estimated(payload)
        appliance_rows.append(dict(usage_id=row['usage_id'],appliance_id=row['appliance_id'],name=snapshot['appliance_name'],
            category=snapshot['category'],category_custom=snapshot['category_custom'],quantity=snapshot['quantity'],estimated_kwh=kwh,
            source=snapshot['source'],estimation_method=snapshot['estimation_method']))
    appliance_rows.sort(key=lambda row:(row['estimated_kwh'] is None,-Decimal(row['estimated_kwh'] or 0),row['name']))
    known=[Decimal(row['estimated_kwh']) for row in appliance_rows if row['estimated_kwh'] is not None]
    total=sum(known,Decimal(0)) if known else None
    focus_bill=by_month.get(focus_month)
    breakdown=[]
    if latest:
        breakdown=[dict(key=key,amount=str(value),percent=None if latest.total_cost==0 else str((value/latest.total_cost*100).quantize(Decimal('.1'),rounding=ROUND_HALF_UP)))
            for key,value in [('energy_cost',latest.energy_cost),('service_charge',latest.service_charge)]]
    return dict(start_month=calendar[0],end_month=end_month,available_months=available,has_data=bool(selected or appliance_rows),
        latest=latest_view,highest=extreme(True),lowest=extreme(False),series=series,cost_breakdown=breakdown,
        appliance_month=focus_month,appliances=appliance_rows,
        appliance_summary=dict(items=len(appliance_rows),estimated_items=len(known),unknown_items=len(appliance_rows)-len(known),estimated_kwh=None if total is None else str(total),
            meter_kwh=focus_bill.units_used if focus_bill else None,
            difference_kwh=None if total is None or focus_bill is None else str(total-Decimal(focus_bill.units_used))))


class AnalysisService:
    def __init__(self,electricity,appliances):self.electricity,self.appliances=electricity,appliances
    def get(self,user_id,months,end_month):
        try:
            bills=self.electricity.list_records(user_id)
            datasets=appliance_data(self.appliances)
            return analyze(user_id,bills,datasets,months,end_month)
        except Exception as error:
            import logging
            logging.getLogger(__name__).warning('Analysis unavailable: %s',type(error).__name__)
            raise StorageUnavailable() from error
