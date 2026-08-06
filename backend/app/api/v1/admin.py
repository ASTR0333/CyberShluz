"""
Admin / Teacher API.

Логически выделено в отдельный роутер. На хакатоне жёсткая авторизация не подключена,
но все эндпоинты потенциально требуют роли TEACHER. Машина состояний стенда:

  FREE → PENDING → DEPLOYING → READY → (FREEZE|CLEANING) → FREE

Все методы, меняющие состояние, обновляют его атомарно через SQLAlchemy session.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.models import Project, Stand, StandStatusEnum, User
from app.core.openstack_client import CapacityExceededException, OpenStackClient
from app.core.security import require_teacher
from app.tasks.deploy import cleanup_stand_task

 
router = APIRouter(dependencies=[Depends(require_teacher)])
logger = logging.getLogger(__name__)


 
 
 
class StandInfo(BaseModel):
    id: int
    status: str
    student_name: Optional[str] = None
    ip_address: Optional[str] = None
    expires_at: Optional[str] = None
    frozen_until: Optional[str] = None
    created_at: Optional[str] = None
    vm_count: int = 0
    vms: Optional[dict] = None
    last_check_result: Optional[dict] = None

    class Config:
        from_attributes = True


class TTLUpdateRequest(BaseModel):
    ttl_hours: int = Field(..., ge=1, le=72, description="Часов до автоочистки (1..72)")


class TTLUpdateResponse(BaseModel):
    stand_id: str
    new_expires_at: str


class GlobalSettings(BaseModel):
    """Глобальные дефолты, применяемые к новым стендам."""

    default_ttl_hours: int = Field(..., ge=1, le=72)
    freeze_duration_hours: int = Field(..., ge=1, le=168)
    max_cluster_utilization: float = Field(..., gt=0.0, le=1.0)


class CapacitySnapshot(BaseModel):
    utilization_pct: float
    threshold_pct: float
    over_threshold: bool
    pool_total: int
    pool_free: int
    pool_active: int
    pool_frozen: int
    pool_cleaning: int


class AdminAction(BaseModel):
    """Минимальный аудит-лог в памяти процесса. Перезаписывается при рестарте."""

    timestamp: str
    actor: str
    action: str
    target: Optional[str] = None
    detail: Optional[str] = None


 
 
_AUDIT_LOG: list[AdminAction] = []


def _audit(actor: str, action: str, target: Optional[str] = None, detail: Optional[str] = None) -> None:
    entry = AdminAction(
        timestamp=datetime.now(timezone.utc).isoformat(),
        actor=actor,
        action=action,
        target=target,
        detail=detail,
    )
    _AUDIT_LOG.append(entry)
    if len(_AUDIT_LOG) > 200:
        del _AUDIT_LOG[:-200]
    logger.info("[AUDIT] %s %s %s %s", actor, action, target or "-", detail or "")


def _serialize_stand(stand: Stand) -> StandInfo:
    vms = None
    vm_count = 0
    if stand.vm_details:
        try:
            vms = json.loads(stand.vm_details)
            vm_count = len(vms)
        except Exception:
            pass

    last_check = None
    if stand.last_check_result:
        try:
            last_check = json.loads(stand.last_check_result)
        except Exception:
            last_check = {"raw": stand.last_check_result}

    return StandInfo(
        id=stand.id,
        status=stand.status.value,
        student_name=stand.owner.lms_id if stand.owner else None,
        ip_address=stand.ip_address,
        expires_at=stand.expires_at.isoformat() if stand.expires_at else None,
        frozen_until=stand.frozen_until.isoformat() if stand.frozen_until else None,
        created_at=stand.created_at.isoformat() if stand.created_at else None,
        vm_count=vm_count,
        vms=vms,
        last_check_result=last_check,
    )


 
 
 
@router.get(
    "/admin/stands",
    response_model=list[StandInfo],
    summary="Список всех стендов",
)
async def list_stands(db: Session = Depends(get_db)):
    stands = db.query(Stand).order_by(Stand.id.asc()).all()
    return [_serialize_stand(s) for s in stands]


@router.get(
    "/admin/stands/{stand_id}",
    response_model=StandInfo,
    summary="Детали конкретного стенда",
)
async def get_stand(stand_id: int, db: Session = Depends(get_db)):
    stand = db.query(Stand).filter(Stand.id == stand_id).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")
    return _serialize_stand(stand)


@router.delete(
    "/admin/stands/{stand_id}",
    summary="Удалить (очистить) стенд",
)
async def delete_stand(stand_id: int, db: Session = Depends(get_db)):
    stand = db.query(Stand).filter(Stand.id == stand_id).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")

    if stand.status == StandStatusEnum.FREE:
        return {"stand_id": str(stand_id), "status": "FREE", "message": "Стенд уже свободен"}
    if stand.status == StandStatusEnum.CLEANING:
        return {"stand_id": str(stand_id), "status": "CLEANING", "message": "Очистка уже идёт"}

    stand.status = StandStatusEnum.CLEANING
    stand.frozen_until = None
    db.commit()
    cleanup_stand_task.delay(stand_id=str(stand_id))
    _audit(actor="teacher", action="cleanup", target=f"stand:{stand_id}")
    return {"stand_id": str(stand_id), "status": "CLEANING", "message": "Удаление запущено"}


@router.put(
    "/admin/stands/{stand_id}/ttl",
    response_model=TTLUpdateResponse,
    summary="Изменить TTL конкретного стенда «на лету»",
)
async def update_stand_ttl(
    stand_id: int,
    request: TTLUpdateRequest,
    db: Session = Depends(get_db),
):
    stand = db.query(Stand).filter(Stand.id == stand_id).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")
    if stand.status in (StandStatusEnum.FREE, StandStatusEnum.CLEANING):
        raise HTTPException(status_code=400, detail="Нельзя изменить TTL неактивного стенда")

    new_expires = datetime.now(timezone.utc) + timedelta(hours=request.ttl_hours)
    stand.expires_at = new_expires
    db.commit()
    _audit(
        actor="teacher",
        action="ttl_update",
        target=f"stand:{stand_id}",
        detail=f"ttl={request.ttl_hours}h",
    )
    return TTLUpdateResponse(stand_id=str(stand_id), new_expires_at=new_expires.isoformat())


@router.post(
    "/admin/stands/{stand_id}/thaw",
    summary="Разморозить замороженный стенд (FREEZE → READY)",
)
async def thaw_stand(stand_id: int, db: Session = Depends(get_db)):
    stand = db.query(Stand).filter(Stand.id == stand_id).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")
    if stand.status != StandStatusEnum.FREEZE:
        raise HTTPException(status_code=400, detail="Стенд не в статусе FREEZE")

    stand.status = StandStatusEnum.READY
    stand.frozen_until = None
    stand.expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.DEFAULT_TTL_HOURS)
    db.commit()
    _audit(actor="teacher", action="thaw", target=f"stand:{stand_id}")
    return {
        "stand_id": str(stand_id),
        "status": "READY",
        "new_expires_at": stand.expires_at.isoformat(),
    }


 
 
 
@router.get(
    "/admin/settings",
    response_model=GlobalSettings,
    summary="Текущие глобальные настройки оркестратора",
)
async def get_settings():
    return GlobalSettings(
        default_ttl_hours=settings.DEFAULT_TTL_HOURS,
        freeze_duration_hours=settings.FREEZE_DURATION_HOURS,
        max_cluster_utilization=settings.MAX_CLUSTER_UTILIZATION,
    )


@router.put(
    "/admin/settings",
    response_model=GlobalSettings,
    summary="Изменить глобальные настройки «на лету»",
    description=(
        "Изменения применяются в рантайме и видны всем новым стендам. "
        "Существующие стенды свои `expires_at` сохраняют."
    ),
)
async def update_settings(payload: GlobalSettings):
    settings.DEFAULT_TTL_HOURS = payload.default_ttl_hours
    settings.FREEZE_DURATION_HOURS = payload.freeze_duration_hours
    settings.MAX_CLUSTER_UTILIZATION = payload.max_cluster_utilization
    _audit(
        actor="teacher",
        action="settings_update",
        detail=(
            f"ttl={payload.default_ttl_hours}h, "
            f"freeze={payload.freeze_duration_hours}h, "
            f"cap={payload.max_cluster_utilization}"
        ),
    )
    return payload


 
@router.put(
    "/admin/default-ttl",
    summary="(legacy) Изменить только TTL по умолчанию",
    deprecated=True,
)
async def update_default_ttl(payload: dict):
    ttl = int(payload.get("default_ttl_hours", settings.DEFAULT_TTL_HOURS))
    settings.DEFAULT_TTL_HOURS = ttl
    return {"default_ttl_hours": ttl}


 
 
 
@router.get(
    "/admin/capacity",
    response_model=CapacitySnapshot,
    summary="Снимок текущей ёмкости КИ + локального пула",
    description=(
        "Возвращает прогнозируемую утилизацию кластера и состояние пула проектов. "
        "Используется UI для предиктивного запрета запуска новых стендов."
    ),
)
async def capacity_snapshot(db: Session = Depends(get_db)):
    try:
        utilization = OpenStackClient().check_capacity(required_vcpus=0)
    except CapacityExceededException as e:
        logger.warning("[ADMIN] Nova API недоступен при опросе ёмкости: %s", e)
        utilization = 0.0
    except Exception as e:
        logger.warning("[ADMIN] Не удалось получить лимиты Nova: %s", e)
        utilization = 0.0

    stands = db.query(Stand).all()
    total = len(stands)
    free = sum(1 for s in stands if s.status == StandStatusEnum.FREE)
    active = sum(
        1
        for s in stands
        if s.status in (StandStatusEnum.READY, StandStatusEnum.DEPLOYING, StandStatusEnum.PENDING)
    )
    frozen = sum(1 for s in stands if s.status == StandStatusEnum.FREEZE)
    cleaning = sum(1 for s in stands if s.status == StandStatusEnum.CLEANING)

    return CapacitySnapshot(
        utilization_pct=round(utilization * 100, 1),
        threshold_pct=round(settings.MAX_CLUSTER_UTILIZATION * 100, 1),
        over_threshold=utilization > settings.MAX_CLUSTER_UTILIZATION,
        pool_total=total,
        pool_free=free,
        pool_active=active,
        pool_frozen=frozen,
        pool_cleaning=cleaning,
    )


@router.get(
    "/admin/pool",
    summary="Состояние пула предсозданных проектов КИ",
)
async def list_pool(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.id.asc()).all()
    result = []
    for p in projects:
        stands = [s for s in p.stands]
        result.append({
            "project_id": p.id,
            "name": p.name,
            "openstack_project_id": p.openstack_project_id,
            "network_id": p.network_id,
            "stand_count": len(stands),
            "stand_statuses": [s.status.value for s in stands],
        })
    return result


 
 
 
@router.get(
    "/admin/audit",
    response_model=list[AdminAction],
    summary="Аудит-лог действий преподавателя (последние 200 событий)",
)
async def get_audit(limit: int = 50):
    limit = max(1, min(200, limit))
    return list(reversed(_AUDIT_LOG[-limit:]))


@router.get(
    "/admin/users",
    summary="Список зарегистрированных пользователей LMS",
)
async def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [
        {
            "id": u.id,
            "lms_id": u.lms_id,
            "role": u.role.value if u.role else None,
            "active_stands": sum(
                1
                for s in u.stands
                if s.status
                in (StandStatusEnum.READY, StandStatusEnum.DEPLOYING, StandStatusEnum.FREEZE)
            ),
        }
        for u in users
    ]
