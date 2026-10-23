from fastapi import APIRouter, Depends, HTTPException, Query, Response
from app.dependencies.auth import require_user
from app.electricity.service import StorageUnavailable
from .schemas import HistoryPage
from .service import history
from uuid import UUID
from app.electricity.routes import same_origin
from .mutations import EditInput, Identity, mutate

router = APIRouter(prefix='/api/history', tags=['History'])


def get_storage():
    from app.electricity import routes
    return routes.service


@router.put('/{record_id}', dependencies=[Depends(same_origin)])
def edit_history(record_id: UUID, data: EditInput, response: Response,
                 user=Depends(require_user), storage=Depends(get_storage)):
    response.headers['Cache-Control'] = 'no-store'
    try: return mutate(storage, user['user_id'], str(record_id), data)
    except StorageUnavailable:
        raise HTTPException(503, 'แก้ไขข้อมูลไม่สำเร็จ กรุณาลองคำขอเดิมอีกครั้งหรือโหลดรายการล่าสุด', headers={'Retry-After':'10'})


@router.delete('/{record_id}', dependencies=[Depends(same_origin)])
def delete_history(record_id: UUID, data: Identity, response: Response,
                   user=Depends(require_user), storage=Depends(get_storage)):
    response.headers['Cache-Control'] = 'no-store'
    try: return mutate(storage, user['user_id'], str(record_id), data, deleting=True)
    except StorageUnavailable:
        raise HTTPException(503, 'ลบข้อมูลไม่สำเร็จ กรุณาลองคำขอเดิมอีกครั้งหรือโหลดรายการล่าสุด', headers={'Retry-After':'10'})



@router.get('', response_model=HistoryPage)
def list_history(response: Response, q: str = Query('', max_length=100),
                 year: int | None = Query(None, ge=1, le=9999),
                 page: int = Query(1, ge=1, le=1000000),
                 page_size: int = Query(6, ge=1, le=100),
                 user: dict = Depends(require_user), storage=Depends(get_storage)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return history(storage, user['user_id'], q, year, page, page_size)
    except StorageUnavailable:
        raise HTTPException(503, 'โหลดประวัติไม่สำเร็จ กรุณาลองใหม่อีกครั้ง',
                            headers={'Retry-After': '5', 'Cache-Control': 'no-store'})
