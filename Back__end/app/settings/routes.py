from fastapi import APIRouter,Depends,Response,HTTPException
from app.dependencies.auth import require_user
from app.electricity.routes import same_origin
from app.electricity.service import StorageUnavailable
from .schemas import SettingsSave,SettingsResult
from .service import service
router=APIRouter(prefix='/api/settings',tags=['Settings'])
def unavailable():return HTTPException(503,'โหลดหรือบันทึกการตั้งค่าไม่สำเร็จ กรุณาตรวจข้อมูลแล้วลองใหม่',headers={'Retry-After':'10','Cache-Control':'no-store'})
@router.get('',response_model=SettingsResult)
def get_settings(response:Response,user=Depends(require_user)):
    response.headers['Cache-Control']='no-store'
    try:return {'settings':service.get(user['user_id'])}
    except StorageUnavailable:raise unavailable()
@router.put('',response_model=SettingsResult,dependencies=[Depends(same_origin)])
def save_settings(data:SettingsSave,response:Response,user=Depends(require_user)):
    response.headers['Cache-Control']='no-store'
    try:return {'settings':service.save(user['user_id'],data)}
    except StorageUnavailable:raise unavailable()
