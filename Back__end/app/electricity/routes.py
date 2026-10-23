import os

from app.core.http_security import origin as normalized_origin

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.dependencies.auth import require_user
from .schemas import ElectricityCreate, ElectricityCreated, ElectricityList
from .service import service, DuplicateMonth, StorageUnavailable

router = APIRouter(prefix="/api/electricity", tags=["Electricity"])


def same_origin(request: Request):
    # Cookie-authenticated mutations reject explicitly cross-site requests.
    # Requests without Origin (CLI/native clients) still require auth + JSON.
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "ไม่อนุญาตคำขอจากเว็บไซต์อื่น")
    if origin:
        source = normalized_origin(origin)
        # Render terminates HTTPS before forwarding HTTP to the container.
        # Use the configured public origin, never untrusted forwarded headers.
        target = normalized_origin(os.getenv("PUBLIC_ORIGIN") or str(request.base_url))
        if source is None or target is None or source != target:
            raise HTTPException(403, "ไม่อนุญาตคำขอจากเว็บไซต์อื่น")
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "กรุณาส่งข้อมูลแบบ application/json")


def unavailable():
    return HTTPException(503, "ระบบบันทึกค่าไฟไม่พร้อมใช้งานชั่วคราว กรุณาตรวจรายการก่อนลองใหม่",
                         headers={"Retry-After": "5"})


@router.post("", response_model=ElectricityCreated, status_code=201, dependencies=[Depends(same_origin)])
def create_electricity(data: ElectricityCreate, response: Response,
                       user: dict = Depends(require_user)):
    response.headers["Cache-Control"] = "no-store"
    try:
        record = service.create(user["user_id"], data)
        return {"message": "บันทึกค่าไฟสำเร็จ", "record": record}
    except DuplicateMonth:
        raise HTTPException(409, "มีข้อมูลค่าไฟของเดือนนี้แล้ว")
    except StorageUnavailable:
        raise unavailable()


@router.get("", response_model=ElectricityList)
def list_electricity(response: Response, user: dict = Depends(require_user)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return {"records": service.list_records(user["user_id"])}
    except StorageUnavailable:
        raise unavailable()
