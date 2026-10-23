"""Explicit production append tool. Requires exact owner, sheet, and --apply.
Run in a short-lived helper container sharing production Redis locks, never load tests.
"""
import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID
from decimal import Decimal
from app.electricity.service import service as electricity
from app.electricity.repository import HEADERS
from app.electricity.schemas import ElectricityRecord
from app.appliances.service import service as appliances, view, estimated
from app.appliances.schemas import UsageInput
from app.appliances.repository import APPLIANCE_HEADERS,USAGE_HEADERS
from demo_dataset import build_dataset,shift,VERSION,MARKER

SHEET='19AIuubmMQdYmT0XHY9xRg3fROLnmm0CBKS-0yZa2YTk'
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--owner',required=True);parser.add_argument('--output',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    owner=str(UUID(args.owner));out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    assert electricity.repository.spreadsheet_id==SHEET and electricity.repository.sheet_name=='electricity_records'
    assert appliances.repository.spreadsheet_id==SHEET and appliances.repository.names==['appliances','appliance_usage_monthly']
    from app.services.auth_user_cache import find_user_by_id
    user=find_user_by_id(owner)
    assert user and user['role']=='user' and user['status']=='active','Active user required'
    client=appliances.repository.client();names=['electricity_records','appliances','appliance_usage_monthly'];headers=[HEADERS,APPLIANCE_HEADERS,USAGE_HEADERS]
    with electricity.sheet_lock() as bill_guard:
      with appliances.sheet_lock() as usage_guard:
        records,_=electricity.repository.load();datasets=appliances.repository.load()
        metadata=client.spreadsheets_get(SHEET,params={'fields':'sheets(properties,tables)'})
        sheets=[next(s for s in metadata['sheets'] if s['properties']['title']==name) for name in names]
        raw=client.values_batch_get(SHEET,[f"'{name}'!A:{['L','R','Z'][i]}" for i,name in enumerate(names)],params={'valueRenderOption':'UNFORMATTED_VALUE'})
        before=[v.get('values',[]) for v in raw['valueRanges']]
        assert all(v and v[0]==h for v,h in zip(before,headers))
        plan_file=out/'plan.json'
        if plan_file.exists():
            plan=json.loads(plan_file.read_text(encoding='utf-8'));assert plan['owner']==owner and plan['version']==VERSION
        else:
            assert not any(MARKER in str(r.get('notes','')) and r['user_id']==owner for r in datasets[0]['rows']), 'Existing seed found without local plan; refusing to guess'
            months=[r.billing_month for r in records if r.user_id==owner]
            end=shift(min(months),-1) if months else '2026-10'
            plan=build_dataset(owner,end);write(plan_file,plan)
        groups=[plan['bills'],plan['masters'],plan['usage']];ids=['record_id','appliance_id','usage_id']
        existing=[{str(row[0]) for row in values[1:] if row} for values in before]
        present=[sum(r[k] in found for r in group) for group,k,found in zip(groups,ids,existing)]
        if present==[24,24,24]:
            print(json.dumps({'already_seeded':True,'counts':present,'usage_month':plan['usage_month']}));return
        assert present==[0,0,0], 'Partial seed exists; inspect manifest before any retry'
        original_months={r.billing_month for r in records if r.user_id==owner}
        assert not original_months.intersection(r['billing_month'] for r in plan['bills']), 'Month conflict'
        for row in plan['usage']:
            parsed=view(row);data=UsageInput.model_validate({k:v for k,v in parsed.items() if k in UsageInput.model_fields})
            assert estimated(data)==row['estimated_kwh']
        write(out/'before.json',{'sheet':SHEET,'headers':headers,'values':before,'hashes':[digest(v) for v in before]})
        requests=[];ranges=[]
        for sheet,values,h,group in zip(sheets,before,headers,groups):
            start=len(values);end=start+24;sid=sheet['properties']['sheetId'];assert end<=sheet['properties']['gridProperties']['rowCount']
            table=next(t for t in sheet['tables'] if t['range'].get('startRowIndex',0)==0 and t['range'].get('startColumnIndex',0)==0)
            assert table['range']['endColumnIndex']==len(h)
            types={p.get('columnIndex',0):p for p in table.get('columnProperties',[])}
            cells=[]
            for record in group:
                row=[]
                for i,column in enumerate(h):
                    value=record.get(column);meta=types.get(i,{})
                    if value is None:row.append({});continue
                    if meta.get('columnType')=='DROPDOWN':
                        allowed={v['userEnteredValue'] for v in meta['dataValidationRule']['condition']['values']};assert str(value) in allowed,(column,value)
                    numeric=meta.get('columnType') in {'DOUBLE','CURRENCY','PERCENT'}
                    row.append({'userEnteredValue':{'numberValue':float(value)}} if numeric else {'userEnteredValue':{'stringValue':str(value)}})
                cells.append({'values':row})
            target={'sheetId':sid,'startRowIndex':start,'endRowIndex':end,'startColumnIndex':0,'endColumnIndex':len(h)}
            for paste in ['PASTE_FORMAT','PASTE_DATA_VALIDATION']:
                requests.append({'copyPaste':{'source':{'sheetId':sid,'startRowIndex':1,'endRowIndex':2,'startColumnIndex':0,'endColumnIndex':len(h)},'destination':target,'pasteType':paste}})
            requests.append({'updateCells':{'range':target,'rows':cells,'fields':'userEnteredValue'}})
            requests.append({'updateTable':{'table':{'tableId':table['tableId'],'range':dict(table['range'],endRowIndex=max(end,table['range']['endRowIndex']))},'fields':'range'}})
            ranges.append({'sheet':sheet['properties']['title'],'start_row':start+1,'end_row':end,'columns':len(h)})
        manifest={'version':VERSION,'owner':owner,'spreadsheet_id':SHEET,'added_per_table':24,'usage_month':plan['usage_month'],'ranges':ranges,'ids':{name:[r[k] for r in group] for name,k,group in zip(names,ids,groups)},'summary':plan['summary'],'original_hashes':[digest(v) for v in before]}
        write(out/'manifest.json',manifest)
        if not args.apply:print(json.dumps({'prepared':True,'ranges':ranges,'summary':plan['summary']}));return
        bill_guard();usage_guard();electricity.cache.delete(electricity.cache_key,appliances.cache_key)
        client.batch_update(SHEET,{'requests':requests})
        after=client.values_batch_get(SHEET,[f"'{name}'!A:{['L','R','Z'][i]}" for i,name in enumerate(names)],params={'valueRenderOption':'UNFORMATTED_VALUE'})
        after=[v.get('values',[]) for v in after['valueRanges']]
        assert all(new[:len(old)]==old for old,new in zip(before,after)), 'Existing values changed'
        for values,group,h,sheet in zip(after,groups,headers,sheets):
            actual={str(row[0]):dict(zip(h,row+['']*(len(h)-len(row)))) for row in values[1:] if row}
            numeric={h[p.get('columnIndex',0)] for p in sheet['tables'][0]['columnProperties'] if p.get('columnType') in {'DOUBLE','CURRENCY','PERCENT'}}
            for record in group:
                found=actual[record[h[0]]]
                for k in h:
                    expected=record.get(k)
                    assert (found[k] in ('',None) if expected is None else Decimal(str(found[k]))==Decimal(str(expected)) if k in numeric else str(found[k])==str(expected)), (k,record[h[0]])
        bill_guard();usage_guard();new_records,_=electricity.repository.load();new_data=appliances.repository.load()
        electricity.cache_records(new_records);appliances.store(new_data)
        manifest.update(verified=True,original_values_unchanged=True,final_counts=[len([r for r in values[1:] if any(r)]) for values in after])
        write(out/'manifest.json',manifest)
        print(json.dumps({'verified':True,'added':[24,24,24],'final_counts':manifest['final_counts'],'usage_month':plan['usage_month'],'summary':plan['summary']}))

if __name__=='__main__':main()
