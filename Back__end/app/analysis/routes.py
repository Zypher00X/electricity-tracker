from datetime import date
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from app.dependencies.auth import require_user
from app.electricity.service import StorageUnavailable
from .service import AnalysisService,shift
router=APIRouter(prefix='/api/analysis',tags=['Analysis'])

def get_service():
    from app.electricity import routes as electricity
    from app.appliances import routes as appliances
    return AnalysisService(electricity.service,appliances.service)

@router.get('')
def get_analysis(response:Response,months:int=Query(12,ge=3,le=12),
                 end_month:str|None=Query(None,pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$'),
                 user=Depends(require_user),service=Depends(get_service)):
    if months not in (3,6,12): raise HTTPException(422,'เลือกช่วง 3, 6 หรือ 12 เดือน')
    if end_month:
        try:date.fromisoformat(end_month+'-01');shift(end_month,1-months)
        except ValueError:raise HTTPException(422,'ช่วงเดือนไม่ถูกต้อง')
    response.headers['Cache-Control']='no-store'
    try:return service.get(user['user_id'],months,end_month)
    except StorageUnavailable:raise HTTPException(503,'โหลดข้อมูลวิเคราะห์ไม่สำเร็จ กรุณาลองใหม่',headers={'Retry-After':'5','Cache-Control':'no-store'})
