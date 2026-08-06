from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.schemas.contracts import CleanupResponse
from app.tasks.deploy import cleanup_stand_task
from app.core.database import get_db
from app.core.models import Stand, StandStatusEnum
from app.core.security import assert_stand_owner_or_teacher, require_student

router = APIRouter()


@router.post(
    "/cleanup/{stand_id}",
    response_model=CleanupResponse,
    summary="Завершить работу и очистить стенд",
    description="Студент завершает лабу — стенд переходит в CLEANING, ВМ удаляются.",
)
async def cleanup_stand(stand_id: int, db: Session = Depends(get_db), user=Depends(require_student)):
    stand = db.query(Stand).filter(Stand.id == stand_id).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")
    assert_stand_owner_or_teacher(user, stand.user_id)

    if stand.status == StandStatusEnum.FREE:
        return CleanupResponse(stand_id=str(stand_id), status="FREE", message="Стенд уже свободен")

    if stand.status == StandStatusEnum.CLEANING:
        return CleanupResponse(stand_id=str(stand_id), status="CLEANING", message="Очистка уже идёт")

    stand.status = StandStatusEnum.CLEANING
    stand.frozen_until = None
    db.commit()

    try:
        cleanup_stand_task.delay(stand_id=stand_id)
    except Exception as exc:
        stand.status = StandStatusEnum.READY
        db.commit()
        raise HTTPException(status_code=503, detail=f"Очередь очистки недоступна: {exc}")
    return CleanupResponse(stand_id=str(stand_id), status="CLEANING", message="Стенд отправлен на очистку")
