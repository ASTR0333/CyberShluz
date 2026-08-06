from app.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.models import Stand, StandStatusEnum
from app.tasks.deploy import cleanup_stand_task
from datetime import datetime, timezone

@celery_app.task(bind=True)
def cleanup_expired_stands(self):
    """
    Проверяет истёкшие стенды и запускает cleanup_stand_task.
    Стенды со статусом FREEZE пропускаются, пока frozen_until не истечёт.
    """
    print("[BEAT] Checking for expired stands...")
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        expired_stands = (
            db.query(Stand)
            .filter(
                Stand.status.in_([StandStatusEnum.READY, StandStatusEnum.DEPLOYING, StandStatusEnum.PENDING]),
                Stand.expires_at.is_not(None),
                Stand.expires_at < now,
            )
            .all()
        )

        for stand in expired_stands:
            print(f"[BEAT] Stand {stand.id} expired. Starting cleanup.")
            stand.status = StandStatusEnum.CLEANING
            db.commit()
            cleanup_stand_task.delay(str(stand.id))

        frozen_expired = (
            db.query(Stand)
            .filter(
                Stand.status == StandStatusEnum.FREEZE,
                Stand.frozen_until.is_not(None),
                Stand.frozen_until < now,
            )
            .all()
        )

        for stand in frozen_expired:
            print(f"[BEAT] Frozen stand {stand.id} thawed. Starting cleanup.")
            stand.status = StandStatusEnum.CLEANING
            stand.frozen_until = None
            db.commit()
            cleanup_stand_task.delay(str(stand.id))
