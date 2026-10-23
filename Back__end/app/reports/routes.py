import hashlib
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from app.dependencies.auth import require_user
from app.electricity.routes import same_origin
from app.electricity.service import feature_redis
from app.advice.routes import get_service as get_advice
from .repository import Repository
from .service import Service

router = APIRouter(prefix='/api/advice/reports', tags=['Saved AI reports'])
repository = Repository()
namespace = hashlib.sha256((repository.spreadsheet_id+':'+repository.sheet_name).encode()).hexdigest()[:16]
service = Service(repository, feature_redis, 'powertrack:reports:'+namespace)
def get_service(): return service

class SaveInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    report_id: UUID

def run(response, callback):
    response.headers['Cache-Control'] = 'no-store'
    try: return callback()
    except HTTPException: raise
    except Exception as exc:
        logging.getLogger(__name__).warning('Reports unavailable: %s', type(exc).__name__)
        raise HTTPException(503, 'โหลดหรือบันทึกรายงานไม่สำเร็จ กรุณาลองใหม่ คำตอบเดิมจะไม่ถูกบันทึกซ้ำ', headers={'Retry-After':'10','Cache-Control':'no-store'}) from None

@router.get('')
def listing(response: Response, month: str | None = Query(None, pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$'),
            page: int = Query(1, ge=1, le=100000), page_size: int = Query(10, ge=1, le=50),
            user=Depends(require_user), reports=Depends(get_service)):
    return run(response, lambda: reports.list(user['user_id'], month, page, page_size))

@router.get('/{report_id}')
def detail(report_id: UUID, response: Response, user=Depends(require_user), reports=Depends(get_service)):
    return run(response, lambda: reports.detail(user['user_id'], str(report_id)))

@router.post('', dependencies=[Depends(same_origin)])
def save(data: SaveInput, response: Response, user=Depends(require_user), reports=Depends(get_service), advice=Depends(get_advice)):
    return run(response, lambda: reports.save(user['user_id'], str(data.report_id), advice))
