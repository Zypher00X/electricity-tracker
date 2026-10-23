from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


Meter = Annotated[StrictInt, Field(ge=0, le=999_999_999)]
Price = Annotated[Decimal, Field(gt=0, le=10000, max_digits=9, decimal_places=4)]
Charge = Annotated[Decimal, Field(ge=0, le=1000000, max_digits=9, decimal_places=2)]


class ElectricityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    billing_month: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    previous_meter: Meter
    current_meter: Meter
    unit_price: Price
    service_charge: Charge

    @field_validator("billing_month")
    @classmethod
    def valid_month(cls, value):
        date.fromisoformat(value + "-01")
        return value

    @field_validator("unit_price", "service_charge", mode="before")
    @classmethod
    def reject_bool(cls, value):
        if isinstance(value, bool):
            raise ValueError("จำนวนเงินต้องเป็นตัวเลข")
        return value

    @model_validator(mode="after")
    def meters_in_order(self):
        if self.current_meter < self.previous_meter:
            raise ValueError("เลขมิเตอร์ปัจจุบันต้องไม่น้อยกว่าเลขมิเตอร์ครั้งก่อน")
        return self


class ElectricityRecord(ElectricityCreate):
    record_id: str
    user_id: str
    units_used: int
    energy_cost: Decimal
    total_cost: Decimal
    created_at: str
    updated_at: str


class ElectricityCreated(BaseModel):
    message: str
    record: ElectricityRecord


class ElectricityList(BaseModel):
    records: list[ElectricityRecord]
