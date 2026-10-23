"""Isolated load target; never imported by production."""
import copy
import os
from advice_runtime import app, mode
from app.reports import routes
from app.reports.service import Service
from app.electricity.service import feature_redis
if not os.getenv('GOOGLE_REPORTS_SHEET','').startswith('test_'): raise RuntimeError('Test reports tab required')
class Fixture:
    def __init__(self): self.records=[];self.loads=0;self.writes=0
    def load(self): self.loads+=1;return copy.deepcopy(self.records),len(self.records)+1
    def insert(self,record,row,guard): guard();self.records.append(copy.deepcopy(record));self.writes+=1
if mode=='synthetic':
    repo=Fixture();routes.service=Service(repo,feature_redis,'test:reports:runtime')
@app.get('/_test/reports')
def info(): return {'isolated':True,'mode':mode,'loads':repo.loads if mode=='synthetic' else None,'writes':repo.writes if mode=='synthetic' else None}
