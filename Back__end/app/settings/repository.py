import os
import threading
from decimal import Decimal
import gspread
from google.oauth2.service_account import Credentials
from .schemas import SettingsRecord

HEADERS='user_id residence_type occupants default_unit_price default_service_charge monthly_budget currency timezone created_at updated_at'.split()

class Repository:
    def __init__(self):
        self.spreadsheet_id=os.getenv('GOOGLE_SPREADSHEET_ID','')
        self.sheet_name=os.getenv('GOOGLE_SETTINGS_SHEET','user_settings')
        self.local=threading.local()
    def client(self):
        if not hasattr(self.local,'client'):
            credentials=Credentials.from_service_account_file(os.getenv('GOOGLE_CREDENTIALS_PATH','/app/credentials/google-service-account.json'),scopes=['https://www.googleapis.com/auth/spreadsheets'])
            self.local.client=gspread.authorize(credentials).http_client
            self.local.client.set_timeout((5,15))
        return self.local.client
    def load(self):
        name=self.sheet_name.replace("'","''")
        rows=self.client().values_get(self.spreadsheet_id,f"'{name}'!A:J",params={'valueRenderOption':'UNFORMATTED_VALUE'}).get('values',[])
        if not rows or rows[0]!=HEADERS:raise ValueError('Settings schema mismatch')
        result=[];seen=set()
        for index,row in enumerate(rows[1:],1):
            if not any(str(value).strip() for value in row):continue
            record=dict(zip(HEADERS,row+['']*(len(HEADERS)-len(row))))
            for field in ['occupants','default_unit_price','default_service_charge','monthly_budget']:
                if record[field]=='':record[field]=None
            if record['occupants'] is not None:
                value=Decimal(str(record['occupants']))
                if value!=value.to_integral_value():raise ValueError('Noninteger occupants')
                record['occupants']=int(value)
            value=SettingsRecord.model_validate(record)
            if value.user_id in seen:raise ValueError('Duplicate settings owner')
            seen.add(value.user_id);result.append((index,value))
        return result,len(rows)
    def save(self,record,row,guard):
        client=self.client();metadata=client.spreadsheets_get(self.spreadsheet_id,params={'fields':'sheets(properties,tables)'})
        sheet=next(s for s in metadata['sheets'] if s['properties']['title']==self.sheet_name)
        sheet_id=sheet['properties']['sheetId'];requests=[]
        if row>=sheet['properties']['gridProperties']['rowCount']:requests.append({'appendDimension':{'sheetId':sheet_id,'dimension':'ROWS','length':1000}})
        cells=[];data=record.model_dump()
        for field in HEADERS:
            value=data[field]
            cells.append({} if value is None else {'userEnteredValue':{'numberValue':float(value)}} if isinstance(value,(Decimal,int)) else {'userEnteredValue':{'stringValue':value}})
        requests.append({'updateCells':{'range':{'sheetId':sheet_id,'startRowIndex':row,'endRowIndex':row+1,'startColumnIndex':0,'endColumnIndex':10},'rows':[{'values':cells}],'fields':'userEnteredValue'}})
        for table in sheet.get('tables',[]):
            if table['range'].get('startRowIndex',0)==0 and table['range'].get('startColumnIndex',0)==0:
                if table['range']['endColumnIndex']!=10:raise ValueError('Settings table width mismatch')
                requests.append({'updateTable':{'table':{'tableId':table['tableId'],'range':dict(table['range'],endRowIndex=max(row+1,table['range']['endRowIndex']))},'fields':'range'}})
        guard();client.batch_update(self.spreadsheet_id,{'requests':requests})
