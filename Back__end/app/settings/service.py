import hashlib
import json
import logging
from datetime import datetime,timezone,timedelta
from fastapi import HTTPException
from gspread.exceptions import APIError
from app.electricity.service import ElectricityService,feature_redis,StorageUnavailable
from .repository import Repository
from .schemas import SettingsRecord

logger=logging.getLogger(__name__)
class Service(ElectricityService):
    def cached_settings(self):
        raw=self.cache.get(self.cache_key)
        if raw is None:return None
        try:return [(int(index),SettingsRecord.model_validate(record)) for index,record in json.loads(raw)]
        except (ValueError,TypeError):self.cache.delete(self.cache_key);return None
    def store(self,rows):self.cache.set(self.cache_key,json.dumps([(index,record.model_dump(mode='json')) for index,record in rows]),ex=30)
    def load(self):
        if self.cache.exists(self.prefix+':cooldown'):raise StorageUnavailable()
        try:return self.repository.load()
        except APIError as error:
            if error.code==429:self.cache.set(self.prefix+':cooldown','1',ex=10)
            raise
    def get(self,user_id):
        try:
            rows=self.cached_settings()
            if rows is None:
                with self.sheet_lock() as guard:
                    rows=self.cached_settings()
                    if rows is None:rows,_=self.load();guard();self.store(rows)
            return next((record for _,record in rows if record.user_id==user_id),None)
        except Exception as error:
            logger.warning('Settings read unavailable: %s',type(error).__name__)
            raise StorageUnavailable() from error
    def save(self,user_id,data):
        try:
            with self.sheet_lock() as guard:
                rows,next_row=self.load()
                old=next(((index,record) for index,record in rows if record.user_id==user_id),None)
                version=old[1].updated_at if old else None
                if version!=data.expected_updated_at:raise HTTPException(409,'การตั้งค่าถูกแก้ไขแล้ว กรุณาโหลดข้อมูลล่าสุดก่อนบันทึก')
                now=datetime.now(timezone(timedelta(hours=7)))
                if old and now<=datetime.fromisoformat(version):now=datetime.fromisoformat(version)+timedelta(microseconds=1)
                timestamp=now.isoformat(timespec='microseconds')
                record=SettingsRecord(**data.model_dump(exclude={'expected_updated_at'}),user_id=user_id,created_at=old[1].created_at if old else timestamp,updated_at=timestamp)
                row=old[0] if old else next_row
                guard();self.cache.delete(self.cache_key)
                self.repository.save(record,row,guard)
                rows=[(index,value) for index,value in rows if value.user_id!=user_id]+[(row,record)]
                try:guard();self.store(rows)
                except Exception:logger.warning('Settings persisted; cache refresh failed')
                return record
        except HTTPException:raise
        except Exception as error:
            logger.warning('Settings write unavailable: %s',type(error).__name__)
            raise StorageUnavailable() from error
repository=Repository()
namespace=hashlib.sha256((repository.spreadsheet_id+':'+repository.sheet_name).encode()).hexdigest()[:16]
service=Service(repository,feature_redis,'powertrack:settings:'+namespace,ttl=30)
