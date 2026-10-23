import calendar
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

Number = Annotated[Decimal, Field(ge=0, le=1000000, max_digits=12, decimal_places=4)]
CATEGORIES = set('air_conditioner refrigerator water_heater computer fan lighting washing_machine television air_purifier dehumidifier humidifier space_heater freezer rice_cooker microwave induction_cooker electric_oven air_fryer electric_kettle coffee_machine toaster blender dishwasher range_hood water_dispenser clothes_dryer iron vacuum_cleaner hair_dryer hair_styler monitor printer router game_console audio_system charger water_pump aquarium security_camera electric_vehicle_charger other'.split())

class UsageInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    billing_month: str = Field(pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$')
    appliance_name: str = Field(min_length=1, max_length=100)
    category: str
    category_custom: str | None = Field(None, max_length=100)
    quantity: Annotated[StrictInt, Field(ge=1, le=1000)] = 1
    brand: str = Field('', max_length=100)
    model: str = Field('', max_length=100)
    rated_power_w: Number | None = None
    average_power_w: Number | None = None
    hours_per_day: Annotated[Decimal, Field(ge=0, le=24, max_digits=6, decimal_places=2)] | None = None
    days_used: Annotated[StrictInt, Field(ge=0, le=31)] | None = None
    monthly_kwh_per_unit: Number | None = None
    estimation_method: Literal['average_power','monthly_kwh'] = 'average_power'
    source: Literal['unknown','measured','manufacturer','energy_label','user_estimate'] = 'unknown'
    notes: str = Field('', max_length=500)

    @field_validator('rated_power_w','average_power_w','hours_per_day','monthly_kwh_per_unit', mode='before')
    @classmethod
    def not_boolean(cls, value):
        if isinstance(value, bool): raise ValueError('Expected a number')
        return value

    @model_validator(mode='after')
    def validate_usage(self):
        parsed = date.fromisoformat(self.billing_month+'-01')
        if self.category not in CATEGORIES: raise ValueError('Invalid category')
        if self.category == 'other' and not self.category_custom: raise ValueError('กรุณาระบุประเภทอื่น ๆ')
        if self.category != 'other': self.category_custom = None
        for field in ('rated_power_w','average_power_w'):
            value = getattr(self,field)
            if value is not None and value <= 0: raise ValueError('Watts must be positive')
        if self.days_used is not None and self.days_used > calendar.monthrange(parsed.year,parsed.month)[1]:
            raise ValueError('จำนวนวันเกินจำนวนวันของเดือน')
        if self.estimation_method == 'average_power':
            self.monthly_kwh_per_unit = None
            if self.source == 'energy_label': raise ValueError('ฉลากหน่วยไฟใช้กับวิธี kWh รายเดือน')
        else:
            self.average_power_w = self.hours_per_day = self.days_used = None
        return self

class UsageUpdate(UsageInput):
    revision: Annotated[StrictInt, Field(ge=1)]

class CancelInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: Annotated[StrictInt, Field(ge=1)]
