"""Deterministic, explicitly synthetic household data; no external I/O."""
import calendar
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from uuid import uuid5, NAMESPACE_URL
from app.electricity.schemas import ElectricityCreate, ElectricityRecord
from app.appliances.schemas import UsageInput
from app.appliances.service import estimated, view

VERSION='demo-20261023-v1'
MARKER='[DEMO:'+VERSION+'] ข้อมูลจำลองสำหรับทดสอบ ไม่ใช่ข้อมูลการใช้ไฟจริง'

def shift(month, delta):
    year,number=map(int,month.split('-'));index=year*12+number-1+delta
    return f'{index//12:04d}-{index%12+1:02d}'

def device_inputs(month):
    # Values are synthetic user estimates, never represented as measured/label facts.
    items=[
      ('แอร์ห้องนอน','air_conditioner',1,500,6,26),
      ('คอมพิวเตอร์ทำงาน','computer',1,120,6,22),
      ('พัดลมห้องนั่งเล่น','fan',2,45,8,30),
      ('หลอดไฟในบ้าน','lighting',6,9,5,30),
      ('ตู้เย็น','refrigerator',1,'monthly',28,None),
      ('เครื่องทำน้ำอุ่น','water_heater',1,3500,'.25',26),
      ('โทรทัศน์','television',1,80,3,26),
      ('เครื่องซักผ้า','washing_machine',1,'monthly',8,None),
      ('หม้อหุงข้าว','rice_cooker',1,500,'.5',26),
      ('ไมโครเวฟ','microwave',1,1000,'.15',20),
      ('หม้อทอดไร้น้ำมัน','air_fryer',1,1400,'.2',12),
      ('กาต้มน้ำ','electric_kettle',1,1500,'.12',26),
      ('เครื่องกดน้ำ','water_dispenser',1,'monthly',12,None),
      ('เราเตอร์','router',1,10,24,31),
      ('จอคอมพิวเตอร์','monitor',1,25,6,22),
      ('เครื่องฟอกอากาศ','air_purifier',1,35,8,26),
      ('เตารีด','iron',1,1000,'.25',8),
      ('ไดร์เป่าผม','hair_dryer',1,1200,'.1',20),
      ('ปั๊มน้ำ','water_pump',1,300,'.3',26),
      ('เครื่องเล่นเกม','game_console',1,150,2,12),
      ('ที่ชาร์จสำรองที่ไม่ได้ใช้','charger',2,10,0,26),
      ('เครื่องดูดฝุ่น','vacuum_cleaner',1,700,'.2',8),
      ('เครื่องพิมพ์ที่ยังไม่ทราบกำลังไฟ','printer',1,None,None,None),
      ('เครื่องเย็บผ้าที่รอวัดกำลังไฟ','other',1,None,None,None),
    ]
    days_in_month=calendar.monthrange(*map(int,month.split('-')))[1]
    result=[]
    for name,category,quantity,watts,hours,days in items:
        data=dict(billing_month=month,appliance_name='[จำลอง] '+name,category=category,quantity=quantity,
                  category_custom='เครื่องเย็บผ้า' if category=='other' else None,notes=MARKER)
        if watts=='monthly':data.update(estimation_method='monthly_kwh',monthly_kwh_per_unit=str(hours),source='user_estimate')
        elif watts is None:data.update(source='unknown')
        else:data.update(average_power_w=str(watts),hours_per_day=str(hours),days_used=min(days,days_in_month),source='user_estimate')
        result.append(UsageInput(**data))
    return result

def build_dataset(owner, end_month='2026-05', timestamp=None):
    timestamp=timestamp or datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='microseconds')
    uid=lambda kind,item:str(uuid5(NAMESPACE_URL,VERSION+':'+owner+':'+kind+':'+str(item)))
    masters=[];usage=[]
    for i,data in enumerate(device_inputs(end_month)):
        aid=uid('appliance',i)
        master=dict(appliance_id=aid,user_id=owner,appliance_name=data.appliance_name,category=data.category,
            brand='',model='',quantity=data.quantity,rated_power_w=None,average_power_w=data.average_power_w,
            power_source=data.source if data.estimation_method=='average_power' else 'unknown',estimation_method=data.estimation_method,
            default_hours_per_day=data.hours_per_day,default_monthly_kwh_per_unit=data.monthly_kwh_per_unit,
            status='active',notes=MARKER,created_at=timestamp,updated_at=timestamp,category_custom=data.category_custom)
        row=dict(usage_id=uid('usage',i),user_id=owner,appliance_id=aid,billing_month=end_month,
            appliance_name_snapshot=data.appliance_name,category_snapshot=data.category,quantity_snapshot=data.quantity,
            rated_power_w_snapshot=None,average_power_w_snapshot=data.average_power_w,power_source_snapshot=master['power_source'],
            estimation_method=data.estimation_method,hours_per_day=data.hours_per_day,days_used=data.days_used,
            monthly_kwh_per_unit=data.monthly_kwh_per_unit,energy_source=data.source if data.estimation_method=='monthly_kwh' else 'unknown',
            estimated_kwh=estimated(data),calculation_version='energy-v1',notes=MARKER,created_at=timestamp,updated_at=timestamp,
            category_custom_snapshot=data.category_custom,brand_snapshot='',model_snapshot='',status='active',revision=1,request_id=uid('request',i))
        view(row)  # Same parser used by the real API.
        masters.append(master);usage.append(row)
    known=sum((Decimal(r['estimated_kwh']) for r in usage if r['estimated_kwh'] is not None),Decimal(0))
    focus_units=int((known*Decimal('1.15')).to_integral_value(rounding=ROUND_CEILING))
    bills=[];meter=10000
    for offset in range(-23,1):
        month=shift(end_month,offset);number=int(month[5:]);units=[250,245,270,310,360,320,290,280,265,255,260,240][number-1]+(offset+23)//12*5
        if offset==0:units=focus_units
        data=ElectricityCreate(billing_month=month,previous_meter=meter,current_meter=meter+units,unit_price='8',service_charge='50')
        energy=(units*data.unit_price).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        bills.append(ElectricityRecord(**data.model_dump(),record_id=uid('bill',month),user_id=owner,units_used=units,
            energy_cost=energy,total_cost=energy+data.service_charge,created_at=timestamp,updated_at=timestamp).model_dump(mode='json'))
        meter+=units
    return {'version':VERSION,'owner':owner,'usage_month':end_month,'bills':bills,'masters':masters,'usage':usage,
            'summary':{'known_kwh':str(known),'known_items':22,'unknown_items':2,'zero_kwh_items':1,'focus_meter_kwh':focus_units}}
