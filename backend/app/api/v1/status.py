import json
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.celery_app import celery_app
from app.schemas.contracts import StandSummaryResponse, StatusResponse
from app.core.database import get_db
from app.core.models import Stand, StandStatusEnum
from app.core.security import assert_stand_owner_or_teacher, require_student
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/stands/my",
    response_model=list[StandSummaryResponse],
    summary="Получить стенды текущего пользователя",
)
async def get_my_stands(db: Session = Depends(get_db), user=Depends(require_student)):
    """The database is the source of truth; browser storage is only a cache."""
    stands = (
        db.query(Stand)
        .filter(
            Stand.user_id == int(user.get("user_id", 0)),
            Stand.status != StandStatusEnum.FREE,
        )
        .order_by(Stand.created_at.desc(), Stand.id.desc())
        .all()
    )
    return [
        StandSummaryResponse(
            stand_id=str(stand.id),
            status=stand.status.value,
            ip_address=stand.ip_address,
            expires_at=stand.expires_at,
            created_at=stand.created_at,
        )
        for stand in stands
    ]

@router.get(
    "/status/{stand_id}",
    response_model=StatusResponse,
    summary="Получить статус стенда",
    description="Возвращает текущий статус стенда из БД и состояние Celery-задачи.",
)
async def get_status(stand_id: str, db: Session = Depends(get_db), user=Depends(require_student)):
    if stand_id in ("latest", "my"):
        stand = (
            db.query(Stand)
            .filter(
                Stand.user_id == int(user.get("user_id", 0)),
                Stand.status != StandStatusEnum.FREE,
            )
            .order_by(Stand.created_at.desc(), Stand.id.desc())
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
    # Redis contains transient Celery progress only; the stand row remains the
    # source of truth. A Redis outage must not make a refreshed status page hang
    # or fail when the database is still available.
    result_state = "PENDING"
    result_info = None
    try:
        task_meta = celery_app.backend.get_task_meta(actual_stand_id)
        result_state = str(task_meta.get("status", "PENDING"))
        result_info = task_meta.get("result")
    except Exception as exc:
        logger.warning("Celery status is unavailable for stand %s: %s", actual_stand_id, exc)
    meta = result_info if isinstance(result_info, dict) else {}

    persisted_error = getattr(stand, "deployment_error", None)
    deployment_updated_at = getattr(stand, "deployment_updated_at", None)
    has_persisted_progress = deployment_updated_at is not None
    backend_failure = result_state == "FAILURE" and not has_persisted_progress
    if (backend_failure or persisted_error) and stand.status.value in ("PENDING", "DEPLOYING"):
        failure_message = persisted_error or meta.get("error") or str(result_info or "Ошибка развертывания")
        return StatusResponse(
            stand_id=actual_stand_id,
            status="FAILED",
            message=failure_message,
            progress=getattr(stand, "deployment_progress", None),
        )

    if stand.status.value == "DEPLOYING":
        last_update = deployment_updated_at or stand.created_at
        if last_update is not None:
            if last_update.tzinfo is None:
                last_update = last_update.replace(tzinfo=timezone.utc)
            stale_after = timedelta(seconds=max(1, settings.DEPLOYMENT_STALE_TIMEOUT))
            if datetime.now(timezone.utc) - last_update > stale_after:
                return StatusResponse(
                    stand_id=actual_stand_id,
                    status="FAILED",
                    message=(
                        "Worker давно не обновлял статус развёртывания. "
                        "Завершите стенд и запустите его повторно."
                    ),
                    progress=getattr(stand, "deployment_progress", None),
                )

    vms = None
    network = None
    if stand.vm_details:
        try:
            vms = json.loads(stand.vm_details)
        except Exception:
            pass
    if stand.network_details:
        try:
            network = json.loads(stand.network_details)
        except Exception:
            pass

    return StatusResponse(
        stand_id=actual_stand_id,
        status=stand.status.value,
        ip_address=stand.ip_address,
        expires_at=stand.expires_at,
        frozen_until=stand.frozen_until,
        message=getattr(stand, "deployment_message", None) or meta.get("message") or "",
        progress=(
            getattr(stand, "deployment_progress", None)
            if getattr(stand, "deployment_progress", None) is not None
            else meta.get("progress")
        ),
        vms=vms,
        network=network,
    )
