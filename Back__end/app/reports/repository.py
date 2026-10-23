"""Immutable reports. Explicit string cells prevent formula interpretation."""
import os
from app.settings.repository import Repository as SheetsRepository

HEADERS = 'report_id user_id billing_month input_hash input_snapshot_json analysis_json provider model prompt_version calculation_version created_at'.split()


class Repository(SheetsRepository):
    def __init__(self):
        super().__init__()
        self.sheet_name = os.getenv('GOOGLE_REPORTS_SHEET', 'ai_reports')

    def load(self):
        name = self.sheet_name.replace("'", "''")
        rows = self.client().values_get(self.spreadsheet_id, f"'{name}'!A:K",
            params={'valueRenderOption': 'UNFORMATTED_VALUE'}).get('values', [])
        if not rows or rows[0] != HEADERS:
            raise ValueError('Reports schema mismatch')
        records = [dict(zip(HEADERS, row + [''] * (11-len(row)))) for row in rows[1:] if any(row)]
        if len({r['report_id'] for r in records}) != len(records):
            raise ValueError('Duplicate report IDs')
        return records, len(rows)

    def insert(self, record, row, guard):
        client = self.client()
        metadata = client.spreadsheets_get(self.spreadsheet_id, params={'fields': 'sheets(properties,tables)'})
        sheet = next(s for s in metadata['sheets'] if s['properties']['title'] == self.sheet_name)
        sheet_id = sheet['properties']['sheetId']
        requests = []
        if row >= sheet['properties']['gridProperties']['rowCount']:
            requests.append({'appendDimension': {'sheetId': sheet_id, 'dimension': 'ROWS', 'length': 1000}})
        requests.append({'updateCells': {'range': {'sheetId': sheet_id, 'startRowIndex': row,
            'endRowIndex': row+1, 'startColumnIndex': 0, 'endColumnIndex': 11},
            'rows': [{'values': [{'userEnteredValue': {'stringValue': record[h]}} for h in HEADERS]}], 'fields': 'userEnteredValue'}})
        for table in sheet.get('tables', []):
            if table['range'].get('startRowIndex', 0) == 0 and table['range'].get('startColumnIndex', 0) == 0:
                if table['range']['endColumnIndex'] != 11: raise ValueError('Reports table width mismatch')
                requests.append({'updateTable': {'table': {'tableId': table['tableId'],
                    'range': dict(table['range'], endRowIndex=max(row+1, table['range']['endRowIndex']))}, 'fields': 'range'}})
        guard()
        client.batch_update(self.spreadsheet_id, {'requests': requests})
