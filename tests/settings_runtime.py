import copy
import os
from auth_cache_runtime import app,mode
from app.settings import routes
from app.settings.service import Service,feature_redis
if not os.getenv('GOOGLE_SETTINGS_SHEET','').startswith('test_'):raise RuntimeError('Test settings tab required')
class Fixture:
    def __init__(self):self.rows=[];self.loads=self.writes=0
    def load(self):self.loads+=1;return copy.deepcopy(self.rows),len(self.rows)+1
    def save(self,record,row,guard):
        guard();self.rows=[(i,r) for i,r in self.rows if i!=row]+[(row,copy.deepcopy(record))];self.writes+=1
if mode=='synthetic':
    repo=Fixture();routes.service=Service(repo,feature_redis,'test:settings:runtime',ttl=30)
@app.get('/_test/settings')
def info():return {'isolated':True,'mode':mode,'loads':repo.loads if mode=='synthetic' else None,'writes':repo.writes if mode=='synthetic' else None}
