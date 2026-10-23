import logging
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from app.dependencies.auth import require_user
from app.history.routes import get_storage
from .service import dashboard

router = APIRouter(prefix='/api/dashboard', tags=['Dashboard'])

@router.get('')
def summary(response: Response, month: str | None = Query(None,pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$'),
            user=Depends(require_user), storage=Depends(get_storage)):
    if month:
        try: date.fromisoformat(month+'-01')
        except ValueError: raise HTTPException(422,'เดือนไม่ถูกต้อง')
    response.headers['Cache-Control']='no-store'
    try: return dashboard(storage,user['user_id'],month)
    except Exception as exc:
        logging.getLogger(__name__).warning('Dashboard unavailable: %s',type(exc).__name__)
        raise HTTPException(503,'โหลดข้อมูลหน้าหลักไม่สำเร็จ กรุณาลองใหม่',headers={'Retry-After':'10','Cache-Control':'no-store'}) from None
