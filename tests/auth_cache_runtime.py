from appliances_runtime import app,mode
from app.dependencies import auth as dependencies
from app.services.auth_user_cache import AuthUserCache
from app.electricity.service import feature_redis
if mode=='synthetic':
    from runtime_app import users
    reads=0
    def load():
        global reads
        reads+=1
        return list(users.values())
    cache=AuthUserCache(feature_redis,'test:auth-users:runtime',load)
    dependencies.find_user_by_id=cache.find
@app.get('/_test/auth-cache')
def cache_info():return dict(isolated=True,mode=mode,source_reads=reads if mode=='synthetic' else None)
