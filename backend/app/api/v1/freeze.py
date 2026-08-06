from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.schemas.contracts import FreezeRequest, FreezeResponse
from app.tasks.deploy import freeze_stand_task
from app.core.database import get_db
from app.core.models import Stand, StandStatusEnum
from app.core.config import settings
from app.core.security import assert_stand_owner_or_teacher, require_student
from datetime import datetime, timedelta, timezone

router = APIRouter()

@router.post(
    "/freeze/{stand_id}",
    response_model=FreezeResponse,
    summary="Заморозить стенд (запрос помощи)",
    description="Студент или преподаватель может заморозить стенд на 24ч для техподдержки.",
)
async def freeze_stand(
    stand_id: int,
    request: FreezeRequest = FreezeRequest(),
    db: Session = Depends(get_db),
    user=Depends(require_student),
):
    stand = db.query(Stand).filter(Stand.id == stand_id).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")
    assert_stand_owner_or_teacher(user, stand.user_id)

    if stand.status == StandStatusEnum.FREE:
        raise HTTPException(status_code=400, detail="Стенд не активен")

    if stand.status == StandStatusEnum.FREEZE:
        return FreezeResponse(
            stand_id=str(stand_id),
            status="FREEZE",
            frozen_until=stand.frozen_until.isoformat() if stand.frozen_until else ""
        )

    frozen_until = datetime.now(timezone.utc) + timedelta(hours=settings.FREEZE_DURATION_HOURS)
    stand.status = StandStatusEnum.FREEZE
    stand.frozen_until = frozen_until
    stand.expires_at = frozen_until
    db.commit()

    freeze_stand_task.apply_async(args=[stand_id, request.reason], task_id=f"freeze_{stand_id}")

    return FreezeResponse(
        stand_id=str(stand_id),
        status="FREEZE",
        frozen_until=frozen_until.isoformat()
    )
