from decimal import Decimal
from typing import Annotated,Literal
from pydantic import BaseModel,ConfigDict,Field,StrictInt,field_validator

class SettingsValues(BaseModel):
    model_config=ConfigDict(extra='forbid')
    residence_type:Literal['dormitory','apartment','house','other','unknown']='unknown'
    occupants:Annotated[StrictInt,Field(ge=1,le=1000)]|None=None
    default_unit_price:Annotated[Decimal,Field(gt=0,le=10000,max_digits=9,decimal_places=4)]|None=None
    default_service_charge:Annotated[Decimal,Field(ge=0,le=1000000,max_digits=9,decimal_places=2)]|None=None
    monthly_budget:Annotated[Decimal,Field(ge=0,le=1000000000,max_digits=12,decimal_places=2)]|None=None
    @field_validator('default_unit_price','default_service_charge','monthly_budget',mode='before')
    @classmethod
    def numeric(cls,value):
        if isinstance(value,bool):raise ValueError('Expected a number')
        return value

class SettingsSave(SettingsValues):
    expected_updated_at:str|None=Field(...,max_length=64)

class SettingsRecord(SettingsValues):
    user_id:str
    currency:Literal['THB']='THB'
    timezone:Literal['Asia/Bangkok']='Asia/Bangkok'
    created_at:str
    updated_at:str

class SettingsResult(BaseModel):
    settings:SettingsRecord|None
