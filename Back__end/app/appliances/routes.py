from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from app.dependencies.auth import require_user
from app.electricity.routes import same_origin
from app.electricity.service import StorageUnavailable
from .schemas import UsageInput, UsageUpdate, CancelInput
from .service import service

router=APIRouter(prefix='/api/appliances',tags=['Appliances'])

def key(idempotency_key: UUID = Header()): return str(idempotency_key)
def unavailable(): return HTTPException(503,'ระบบเครื่องใช้ไฟฟ้าไม่พร้อมใช้งาน กรุณาตรวจรายการก่อนลองใหม่',headers={'Retry-After':'5','Cache-Control':'no-store'})

@router.get('')
def list_usage(response:Response,billing_month:str=Query(pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$'),user=Depends(require_user)):
    from datetime import date
    try: date.fromisoformat(billing_month+'-01')
    except ValueError: raise HTTPException(422,'เดือนที่ระบุไม่ถูกต้อง')
    response.headers['Cache-Control']='no-store'
    try: return {'records':service.list(user['user_id'],billing_month)}
    except StorageUnavailable: raise unavailable()

@router.post('',status_code=201,dependencies=[Depends(same_origin)])
def create(data:UsageInput,response:Response,user=Depends(require_user),request_id=Depends(key)):
    response.headers['Cache-Control']='no-store'
    try: return {'record':service.save(user['user_id'],data,request_id),'message':'บันทึกเครื่องใช้และการใช้งานสำเร็จ'}
    except StorageUnavailable: raise unavailable()

@router.put('/{usage_id}',dependencies=[Depends(same_origin)])
def update(usage_id:UUID,data:UsageUpdate,response:Response,user=Depends(require_user),request_id=Depends(key)):
    response.headers['Cache-Control']='no-store'
    payload=UsageInput.model_validate(data.model_dump(exclude={'revision'}))
    try: return {'record':service.save(user['user_id'],payload,request_id,str(usage_id),data.revision),'message':'แก้ไขข้อมูลการใช้งานสำเร็จ'}
    except StorageUnavailable: raise unavailable()

@router.post('/{usage_id}/cancel',dependencies=[Depends(same_origin)])
def cancel(usage_id:UUID,data:CancelInput,response:Response,user=Depends(require_user),request_id=Depends(key)):
    response.headers['Cache-Control']='no-store'
    try: return {'record':service.save(user['user_id'],None,request_id,str(usage_id),data.revision,True),'message':'ยกเลิกรายการแล้ว โดยยังเก็บประวัติไว้'}
    except StorageUnavailable: raise unavailable()
