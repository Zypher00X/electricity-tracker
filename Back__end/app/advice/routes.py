import hashlib
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from app.dependencies.auth import require_user
from app.electricity.routes import same_origin
from app.electricity.service import feature_redis, StorageUnavailable
from .context import Context
from .service import AdviceService
from .schemas import ChatInput
from .export_prompt import ExportInput, ExportService

router = APIRouter(prefix='/api/advice', tags=['Advice'])


def get_service():
    from app.electricity import routes as electricity
    from app.appliances import routes as appliances
    from app.settings import routes as settings
    namespace = hashlib.sha256((electricity.service.prefix + appliances.service.prefix + settings.service.prefix).encode()).hexdigest()[:16]
    return AdviceService(Context(electricity.service, appliances.service, settings.service), feature_redis, 'powertrack:advice:' + namespace)


def unavailable():
    return HTTPException(503, 'โหลดข้อมูลสำหรับคำแนะนำไม่สำเร็จ กรุณาลองใหม่', headers={'Retry-After': '10', 'Cache-Control': 'no-store'})


@router.get('/context')
def context(response: Response, month: str | None = Query(None, pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$'),
            user=Depends(require_user), service=Depends(get_service)):
    if month:
        from datetime import date
        try:
            if date.fromisoformat(month + '-01').year < 2: raise ValueError()
        except ValueError: raise HTTPException(422, 'เดือนไม่ถูกต้อง')
    response.headers['Cache-Control'] = 'no-store'
    try: return service.get_context(user['user_id'], month)
    except StorageUnavailable: raise unavailable()


@router.post('/chat', dependencies=[Depends(same_origin)])
def chat(data: ChatInput, response: Response, user=Depends(require_user), service=Depends(get_service)):
    response.headers['Cache-Control'] = 'no-store'
    try: return service.respond(user['user_id'], data)
    except StorageUnavailable: raise unavailable()


@router.post('/export-prompt', dependencies=[Depends(same_origin)])
def export_prompt(data: ExportInput, response: Response, user=Depends(require_user), service=Depends(get_service)):
    response.headers['Cache-Control'] = 'no-store'
    try: return ExportService(service).create(user['user_id'], data.month)
    except StorageUnavailable: raise unavailable()
