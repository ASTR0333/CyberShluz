"""Return owner-scoped Cyber Infrastructure console links for Windows VMs."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.models import Stand, StandStatusEnum
from app.core.security import assert_stand_owner_or_teacher, require_student

router = APIRouter()
_CONSOLE_READY_STATUSES = (StandStatusEnum.READY, StandStatusEnum.FREEZE)


def _windows_server_id(stand: Stand, vm_role: str) -> str:
    normalized_role = vm_role.strip().upper()
    if not normalized_role.startswith("W"):
        raise HTTPException(
            status_code=422,
            detail="Веб-консоль доступна только для Windows-машин с ролью W*",
        )
    try:
        vms = json.loads(stand.vm_details or "{}")
        role = next(role for role in vms if role.upper() == normalized_role)
        return str(UUID(str(vms[role]["server_id"])))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=409,
            detail=f"В топологии стенда нет корректного UUID {normalized_role}",
        ) from exc
    except StopIteration as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Windows-машина {normalized_role} не найдена в топологии стенда",
        ) from exc


def _create_console_link(
    stand_id: str,
    vm_role: str,
    db: Session,
    user,
):
    try:
        numeric_id = int(stand_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный идентификатор стенда") from exc

    stand = db.query(Stand).filter(Stand.id == numeric_id).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")
    assert_stand_owner_or_teacher(user, stand.user_id)
    if stand.status not in _CONSOLE_READY_STATUSES:
        raise HTTPException(status_code=409, detail="Стенд ещё не готов к подключению")

    normalized_role = vm_role.strip().upper()
    server_id = _windows_server_id(stand, normalized_role)
    dashboard_url = settings.OS_DASHBOARD_URL.rstrip("/")
    if not dashboard_url:
        raise HTTPException(status_code=503, detail="Адрес панели КИ не настроен")

    return {
        "launch_url": (
            f"{dashboard_url}/compute/servers/instances/{server_id}/console"
        ),
        "server_id": server_id,
        "vm_role": normalized_role,
    }


@router.post("/stand/{stand_id}/console/{vm_role}", summary="Открыть консоль Windows-машины в КИ")
def create_vm_console_link(
    stand_id: str,
    vm_role: str,
    db: Session = Depends(get_db),
    user=Depends(require_student),
):
    return _create_console_link(stand_id, vm_role, db, user)


@router.post("/stand/{stand_id}/console", summary="Открыть консоль W-DC в КИ")
def create_console_link(
    stand_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_student),
):
    """Compatibility endpoint retained for clients that only know about W-DC."""
    response = _create_console_link(stand_id, "W-DC", db, user)
    return {"launch_url": response["launch_url"], "server_id": response["server_id"]}
