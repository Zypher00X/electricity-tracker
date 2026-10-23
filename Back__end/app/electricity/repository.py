"""Bounded network calls and atomic row/table writes to the existing worksheet."""
import os
import threading
from decimal import Decimal

import gspread
from google.oauth2.service_account import Credentials

from .schemas import ElectricityRecord

HEADERS = ["record_id", "user_id", "billing_month", "previous_meter", "current_meter",
           "units_used", "unit_price", "service_charge", "energy_cost", "total_cost",
           "created_at", "updated_at"]


class SheetRepository:
    def __init__(self):
        self.local = threading.local()
        self.spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", "")
        self.sheet_name = os.getenv("GOOGLE_ELECTRICITY_SHEET", "electricity_records")

    def connection(self):
        # requests sessions are reused per thread, never shared concurrently.
        if not hasattr(self.local, "client"):
            credentials = Credentials.from_service_account_file(
                os.getenv("GOOGLE_CREDENTIALS_PATH", "/app/credentials/google-service-account.json"),
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            client = gspread.authorize(credentials).http_client
            client.set_timeout((5, 15))
            metadata = client.spreadsheets_get(self.spreadsheet_id, params={"fields": "sheets(properties,tables)"})
            sheet = next(s for s in metadata["sheets"] if s["properties"]["title"] == self.sheet_name)
            tables = [t for t in sheet.get("tables", []) if t["range"].get("startRowIndex", 0) == 0
                      and t["range"].get("startColumnIndex", 0) == 0
                      and t["range"]["endColumnIndex"] == len(HEADERS)]
            if len(tables) != 1:
                raise ValueError("Electricity native table is missing or ambiguous")
            self.local.sheet_id = sheet["properties"]["sheetId"]
            self.local.table_id = tables[0]["tableId"]
            self.local.client = client
        return self.local.client

    def load(self):
        records, _, next_row = self.load_indexed()
        return records, next_row

    def load_indexed(self):
        client = self.connection()
        escaped = self.sheet_name.replace("'", "''")
        result = client.values_get(self.spreadsheet_id, f"'{escaped}'!A:L", params={"valueRenderOption": "UNFORMATTED_VALUE"})
        values = result.get("values", [])
        if not values or values[0] != HEADERS:
            raise ValueError("electricity_records header does not match schema")
        records, positions = [], {}
        for index, row in enumerate(values[1:], 1):
            if not any(str(v).strip() for v in row):
                continue
            data = dict(zip(HEADERS, row + [""] * (len(HEADERS) - len(row))))
            # Sheets returns whole-number numeric cells as ints/floats.
            for field in ("previous_meter", "current_meter"):
                value = Decimal(str(data[field]))
                if value != value.to_integral_value():
                    raise ValueError("Non-integer meter in stored data")
                data[field] = int(value)
            record = ElectricityRecord.model_validate(data)
            if record.record_id in positions: raise ValueError('Duplicate electricity record ID')
            records.append(record)
            positions[record.record_id] = index
        return records, positions, len(values)

    def replace(self, record, row, guard):
        client = self.connection()
        payload = record.model_dump()
        cells = [{'userEnteredValue': {'numberValue': float(payload[name])}} if isinstance(payload[name], (Decimal, int))
                 else {'userEnteredValue': {'stringValue': payload[name]}} for name in HEADERS]
        guard()
        client.batch_update(self.spreadsheet_id, {'requests': [{'updateCells': {
            'range': {'sheetId': self.local.sheet_id, 'startRowIndex': row, 'endRowIndex': row+1,
                      'startColumnIndex': 0, 'endColumnIndex': len(HEADERS)},
            'rows': [{'values': cells}], 'fields': 'userEnteredValue'}}]})

    def remove(self, row, guard):
        client = self.connection()
        # Clear only this record's A:L cells. Other owners' rows, formatting and
        # the native table stay in place; source reads skip the empty row.
        guard()
        client.batch_update(self.spreadsheet_id, {'requests': [{'updateCells': {
            'range': {'sheetId': self.local.sheet_id, 'startRowIndex': row, 'endRowIndex': row+1,
                      'startColumnIndex': 0, 'endColumnIndex': len(HEADERS)},
            'rows': [{'values': [{} for _ in HEADERS]}], 'fields': 'userEnteredValue'}}]})

    def insert(self, record, next_row, guard):
        client = self.connection()
        payload = record.model_dump()
        cells = []
        for name in HEADERS:
            value = payload[name]
            if isinstance(value, Decimal):
                cells.append({"userEnteredValue": {"numberValue": float(value)}})
            elif isinstance(value, int):
                cells.append({"userEnteredValue": {"numberValue": value}})
            else:
                cells.append({"userEnteredValue": {"stringValue": value}})
        sheet_id = self.local.sheet_id
        # Grow the grid if necessary; native table coverage is updated atomically
        # with the new row. No automatic append retry after an ambiguous timeout.
        metadata = client.spreadsheets_get(self.spreadsheet_id, params={"fields": "sheets(properties)"})
        props = next(s["properties"] for s in metadata["sheets"] if s["properties"]["sheetId"] == sheet_id)
        requests = []
        if next_row >= props["gridProperties"]["rowCount"]:
            requests.append({"appendDimension": {"sheetId": sheet_id, "dimension": "ROWS", "length": 1000}})
        requests += [
            {"updateCells": {"range": {"sheetId": sheet_id, "startRowIndex": next_row,
                "endRowIndex": next_row + 1, "startColumnIndex": 0, "endColumnIndex": len(HEADERS)},
                "rows": [{"values": cells}], "fields": "userEnteredValue"}},
            {"updateTable": {"table": {"tableId": self.local.table_id, "range": {
                "sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": next_row + 1,
                "startColumnIndex": 0, "endColumnIndex": len(HEADERS)}}, "fields": "range"}},
        ]
        guard()
        client.batch_update(self.spreadsheet_id, {"requests": requests})
