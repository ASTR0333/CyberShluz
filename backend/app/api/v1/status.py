import json
from fastapi import APIRouter, HTTPException, Depends
from celery.result import AsyncResult
from sqlalchemy.orm import Session
from app.celery_app import celery_app
from app.schemas.contracts import StatusResponse
from app.core.database import get_db
from app.core.models import Stand
from app.core.security import assert_stand_owner_or_teacher, require_student

router = APIRouter()

@router.get(
    "/status/{stand_id}",
    response_model=StatusResponse,
    summary="Получить статус стенда",
    description="Возвращает текущий статус стенда из БД и состояние Celery-задачи.",
)
async def get_status(stand_id: str, db: Session = Depends(get_db), user=Depends(require_student)):
    if stand_id == "latest":
        stand = db.query(Stand).order_by(Stand.id.desc()).first()
    elif stand_id == "my":
         
        from app.core.security import UserRole
        if user.get("role") in (UserRole.TEACHER, UserRole.ADMIN):
            stand = db.query(Stand).order_by(Stand.id.desc()).first()
        else:
            stand = (
                db.query(Stand)
                .filter(Stand.user_id == int(user.get("user_id", 0)))
                .order_by(Stand.id.desc())
                .first()
            )
        if not stand:
            raise HTTPException(status_code=404, detail="Стенд не найден")
    else:
        try:
            stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid stand ID format")

    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")

    assert_stand_owner_or_teacher(user, stand.user_id)

     
    actual_stand_id = str(stand.id)
    result = AsyncResult(actual_stand_id, app=celery_app)
    meta = result.info if isinstance(result.info, dict) else {}

    if result.state == "FAILURE" and stand.status.value in ("PENDING", "DEPLOYING"):
        return StatusResponse(
            stand_id=actual_stand_id,
            status="FAILED",
            message=str(meta.get("error", "Ошибка развертывания"))
        )

    vms = None
    if stand.vm_details:
        try:
            vms = json.loads(stand.vm_details)
        except Exception:
            pass

    return StatusResponse(
        stand_id=actual_stand_id,
        status=stand.status.value,
        ip_address=stand.ip_address,
        expires_at=stand.expires_at,
        frozen_until=stand.frozen_until,
        message=meta.get("message", ""),
        vms=vms,
    )
