import copy
import os
from runtime_app import app, mode
from app.appliances import routes
from app.appliances.service import Service, feature_redis

class ApplianceFixture:
    def __init__(self):
        self.loads=self.writes=0
        self.data=[{'rows':[],'next':1,'sheet':{}},{'rows':[],'next':1,'sheet':{}}]
    def load(self):self.loads+=1;return copy.deepcopy(self.data)
    def commit(self,changes,guard):
        guard()
        for _,record,index,headers in changes:
            target=self.data[0 if 'appliance_name' in record else 1]
            target['rows']=[r for r in target['rows'] if r['_row']!=index]+[dict(record,_row=index)]
            target['next']=max(target['next'],index+1)
        self.writes+=1

if not all(os.getenv(name,'').startswith('test_') for name in ['GOOGLE_APPLIANCES_SHEET','GOOGLE_USAGE_SHEET']):
    raise RuntimeError('Use test appliance worksheets only')
if mode=='synthetic':
    repo=ApplianceFixture()
    routes.service=Service(repo,feature_redis,'test:appliances:runtime',ttl=30)

@app.get('/_test/appliances')
def info():
    return dict(isolated=True,mode=mode,loads=repo.loads if mode=='synthetic' else None,writes=repo.writes if mode=='synthetic' else None)
