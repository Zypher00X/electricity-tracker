from decimal import Decimal
from pydantic import BaseModel
from app.electricity.schemas import ElectricityRecord


class HistoryRecord(ElectricityRecord):
    change_percent: Decimal | None = None


class HistoryPage(BaseModel):
    records: list[HistoryRecord]
    total: int
    page: int
    page_size: int
    total_pages: int
    available_years: list[int]
