"""Map shared storage failures to a bounded, non-sensitive retry response."""
import logging
from fastapi.responses import JSONResponse
from gspread.exceptions import APIError
from redis.exceptions import RedisError

async def storage_unavailable(request,error):
    logging.getLogger(__name__).warning('Storage unavailable: %s code=%s',type(error).__name__,getattr(error,'code',None))
    return JSONResponse(status_code=503,content={'detail':'บริการข้อมูลไม่พร้อมใช้งานชั่วคราว กรุณาลองใหม่'},headers={'Retry-After':'10','Cache-Control':'no-store'})

def install_storage_handlers(app):
    app.add_exception_handler(APIError,storage_unavailable)
    app.add_exception_handler(RedisError,storage_unavailable)
