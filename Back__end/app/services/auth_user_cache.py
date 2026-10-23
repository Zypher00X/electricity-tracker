"""Short-lived public auth snapshot, never passwords/tokens; sessions remain live."""
import hashlib
import json
import threading
from fastapi import HTTPException
from gspread.exceptions import APIError
from app.repositories.google_sheets import get_google_sheets_client, GOOGLE_SPREADSHEET_ID, GOOGLE_USERS_SHEET
from app.electricity.service import ElectricityService, feature_redis, StorageUnavailable

FIELDS=('user_id','full_name','email','phone','role','status')
_local=threading.local()

def load_users():
    if not hasattr(_local,'client'):
        _local.client=get_google_sheets_client().http_client
        _local.client.set_timeout((5,15))
    name=GOOGLE_USERS_SHEET.replace("'","''")
    values=_local.client.values_get(GOOGLE_SPREADSHEET_ID,f"'{name}'!A:L",params={'valueRenderOption':'FORMATTED_VALUE'}).get('values',[])
    if not values or not all(field in values[0] for field in FIELDS): raise ValueError('Users schema mismatch')
    headers=values[0]
    return [{field:str(dict(zip(headers,row)).get(field,'')) for field in FIELDS} for row in values[1:] if any(str(value).strip() for value in row)]

class AuthUserCache(ElectricityService):
    def __init__(self,cache,prefix,loader=load_users):
        super().__init__(None,cache,prefix,ttl=10);self.loader=loader
    def snapshot(self):
        raw=self.cache.get(self.cache_key)
        if raw is None:return None
        try:
            users=json.loads(raw)
            if not isinstance(users,list) or any(not isinstance(user,dict) or not all(field in user for field in FIELDS) for user in users):raise ValueError()
            return users
        except (ValueError,TypeError):self.cache.delete(self.cache_key);return None
    def find(self,user_id):
        try:
            users=self.snapshot()
            # A newly registered user can be absent from the previous snapshot.
            if users is not None:
                match=next((user for user in users if user['user_id']==user_id),None)
                if match is not None:return match
            with self.sheet_lock() as guard:
                users=self.snapshot()
                if users is not None:
                    match=next((user for user in users if user['user_id']==user_id),None)
                    if match is not None:return match
                if self.cache.exists(self.prefix+':cooldown'):raise StorageUnavailable()
                try:users=self.loader()
                except APIError as error:
                    if getattr(error,'code',None)==429:self.cache.set(self.prefix+':cooldown','1',ex=10)
                    raise
                users=[{field:str(user.get(field,'')) for field in FIELDS} for user in users]
                for user in users:user['user_id']=user['user_id'].strip()
                ids=[user['user_id'] for user in users]
                if not all(ids) or len(set(ids))!=len(ids):raise ValueError('Ambiguous user identity')
                guard();self.cache.set(self.cache_key,json.dumps(users),ex=10)
                return next((user for user in users if user['user_id']==user_id),None)
        except HTTPException:raise
        except Exception:
            # Fail closed: never fall back to expired authorization data.
            raise HTTPException(503,'ระบบตรวจสอบบัญชีไม่พร้อมใช้งานชั่วคราว กรุณาลองใหม่',headers={'Retry-After':'10','Cache-Control':'no-store'})

namespace=hashlib.sha256(f'{GOOGLE_SPREADSHEET_ID}:{GOOGLE_USERS_SHEET}'.encode()).hexdigest()[:16]
auth_user_cache=AuthUserCache(feature_redis,'powertrack:auth-users:'+namespace)

def find_user_by_id(user_id):return auth_user_cache.find(str(user_id).strip())
