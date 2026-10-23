import os
import threading
from decimal import Decimal
import gspread
from google.oauth2.service_account import Credentials

APPLIANCE_HEADERS = 'appliance_id user_id appliance_name category brand model quantity rated_power_w average_power_w power_source estimation_method default_hours_per_day default_monthly_kwh_per_unit status notes created_at updated_at category_custom'.split()
USAGE_HEADERS = 'usage_id user_id appliance_id billing_month appliance_name_snapshot category_snapshot quantity_snapshot rated_power_w_snapshot average_power_w_snapshot power_source_snapshot estimation_method hours_per_day days_used monthly_kwh_per_unit energy_source estimated_kwh calculation_version notes created_at updated_at category_custom_snapshot brand_snapshot model_snapshot status revision request_id'.split()

class Repository:
    def __init__(self):
        self.spreadsheet_id=os.getenv('GOOGLE_SPREADSHEET_ID','')
        self.names=[os.getenv('GOOGLE_APPLIANCES_SHEET','appliances'),os.getenv('GOOGLE_USAGE_SHEET','appliance_usage_monthly')]
        self.local=threading.local()
    def client(self):
        if not hasattr(self.local,'client'):
            credentials=Credentials.from_service_account_file(os.getenv('GOOGLE_CREDENTIALS_PATH','/app/credentials/google-service-account.json'),scopes=['https://www.googleapis.com/auth/spreadsheets'])
            self.local.client=gspread.authorize(credentials).http_client
            self.local.client.set_timeout((5,15))
        return self.local.client
    def load(self):
        client=self.client()
        metadata=client.spreadsheets_get(self.spreadsheet_id,params={'fields':'sheets(properties,tables)'})
        sheets=[next(s for s in metadata['sheets'] if s['properties']['title']==name) for name in self.names]
        ranges=["'"+name.replace("'","''")+"'!A:Z" for name in self.names]
        result=client.values_batch_get(self.spreadsheet_id,ranges,params={'valueRenderOption':'UNFORMATTED_VALUE'})
        data=[]
        for sheet,values,headers in zip(sheets,result['valueRanges'],[APPLIANCE_HEADERS,USAGE_HEADERS]):
            rows=values.get('values',[])
            if not rows or rows[0]!=headers: raise ValueError('Appliance schema mismatch')
            entries=[]
            for index,row in enumerate(rows[1:],1):
                if not any(str(v).strip() for v in row): continue
                item=dict(zip(headers,row+['']*(len(headers)-len(row))))
                item['_row']=index
                entries.append(item)
            data.append({'rows':entries,'next':len(rows),'sheet':sheet})
        return data
    def commit(self, changes, guard):
        requests=[]
        for dataset,record,row,headers in changes:
            props=dataset['sheet']['properties'];sheet_id=props['sheetId']
            if row>=props['gridProperties']['rowCount']:
                requests.append({'appendDimension':{'sheetId':sheet_id,'dimension':'ROWS','length':1000}})
            cells=[]
            for header in headers:
                value=record.get(header)
                if header == 'estimated_kwh' and value is not None:
                    value=Decimal(str(value))
                if value is None: cells.append({})
                elif isinstance(value,(int,float,Decimal)) and not isinstance(value,bool): cells.append({'userEnteredValue':{'numberValue':float(value)}})
                else: cells.append({'userEnteredValue':{'stringValue':str(value)}})
            requests.append({'updateCells':{'range':{'sheetId':sheet_id,'startRowIndex':row,'endRowIndex':row+1,'startColumnIndex':0,'endColumnIndex':len(headers)},'rows':[{'values':cells}],'fields':'userEnteredValue'}})
            for table in dataset['sheet'].get('tables',[]):
                if table['range'].get('startRowIndex',0)==0 and table['range'].get('startColumnIndex',0)==0:
                    requests.append({'updateTable':{'table':{'tableId':table['tableId'],'range':{'sheetId':sheet_id,'startRowIndex':0,'endRowIndex':max(row+1,table['range']['endRowIndex']),'startColumnIndex':0,'endColumnIndex':len(headers)}},'fields':'range'}})
        guard()
        self.client().batch_update(self.spreadsheet_id,{'requests':requests})
