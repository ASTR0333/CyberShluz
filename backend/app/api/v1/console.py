"""Return owner-scoped Cyber Infrastructure console links for W-DC."""
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


def _wdc_server_id(stand: Stand) -> str:
    try:
        vms = json.loads(stand.vm_details or "{}")
        return str(UUID(str(vms["W-DC"]["server_id"])))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=409,
            detail="В топологии стенда нет корректного UUID W-DC",
        ) from exc


@router.post("/stand/{stand_id}/console", summary="Открыть консоль W-DC в КИ")
def create_console_link(
    stand_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_student),
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

    server_id = _wdc_server_id(stand)
    dashboard_url = settings.OS_DASHBOARD_URL.rstrip("/")
    if not dashboard_url:
        raise HTTPException(status_code=503, detail="Адрес панели КИ не настроен")

    return {
        "launch_url": (
            f"{dashboard_url}/compute/servers/instances/{server_id}/console"
        ),
        "server_id": server_id,
    }
