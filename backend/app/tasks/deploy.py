import json
from app.celery_app import celery_app
from datetime import datetime, timedelta, timezone
from app.core.openstack_client import OpenStackClient, CapacityExceededException
from app.core.config import settings


@celery_app.task(bind=True, max_retries=2)
def deploy_stand_task(self, stand_id: str, user_id: str, lab_id: int, role: str = "student"):
    from app.core.database import SessionLocal
    from app.core.models import Stand, StandStatusEnum

    print(f"[WORKER] Starting deployment for stand_id={stand_id}, user={user_id}, lab={lab_id}")

    with SessionLocal() as db:
        stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
        if stand:
            stand.status = StandStatusEnum.DEPLOYING
            db.commit()

    def progress_cb(pct, msg):
        self.update_state(state="DEPLOYING", meta={"progress": pct, "message": msg})

    try:
        progress_cb(5, "Подключение к Кибер Инфраструктуре...")
        os_client = OpenStackClient()

        key_name = f"key-stand{stand_id}"
        progress_cb(10, "Генерация SSH-ключа...")
        private_key = os_client.create_keypair(key_name)

        progress_cb(20, "Проверка ёмкости кластера...")
        utilization = os_client.get_cluster_utilization()
        if utilization > settings.MAX_CLUSTER_UTILIZATION:
            raise CapacityExceededException(
                f"Кластер перегружен ({utilization*100:.1f}%)"
            )

        progress_cb(30, "Развёртывание топологии Лаб. №3 (5 ВМ)...")
        vm_results = os_client.deploy_lab3_stand(stand_id, key_name, progress_cb)
         
        net_details = vm_results.pop("__network__", None)

        lms = vm_results.get("L-MS", {})
        access_ip = lms.get("floating_ip")
        if not access_ip:
            raise CapacityExceededException("Не удалось получить публичный IP адрес (возможно, исчерпан лимит)")

        active_count = sum(1 for v in vm_results.values() if v.get("status") == "ACTIVE")
        total_count = len(vm_results)
        ssh_bootstrapped = vm_results.get("L-MS", {}).get("ssh_bootstrapped", True)

        with SessionLocal() as db:
            stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
            if stand:
                stand.ip_address = access_ip
                stand.private_key = private_key
                stand.status = StandStatusEnum.READY
                stand.vm_details = json.dumps(vm_results, default=str)
                if net_details:
                    stand.network_details = json.dumps(net_details, default=str)
                now = datetime.now(timezone.utc)
                stand.expires_at = now + timedelta(hours=settings.DEFAULT_TTL_HOURS)
                db.commit()

        if ssh_bootstrapped:
            progress_cb(100, f"Стенд готов! {active_count}/{total_count} ВМ активны.")
        else:
            progress_cb(100, f"Стенд готов ({active_count}/{total_count} ВМ), но SSH-ключ не был автоматически настроен. Обратитесь к преподавателю.")
        return {
            "stand_id": stand_id,
            "ip_address": access_ip,
            "status": "READY",
            "vms": vm_results,
        }

    except CapacityExceededException as ce:
        with SessionLocal() as db:
            stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
            if stand:
                stand.status = StandStatusEnum.FREE
                stand.user_id = None
                db.commit()
        self.update_state(state="FAILED", meta={"error": str(ce)})
        raise self.retry(exc=ce, countdown=180)

    except Exception as exc:
        print(f"[WORKER] Deploy failed: {exc}")
        with SessionLocal() as db:
            stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
            if stand and stand.status == StandStatusEnum.DEPLOYING:
                stand.status = StandStatusEnum.FREE
                stand.user_id = None
                stand.ip_address = None
                stand.private_key = None
                db.commit()
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True)
def freeze_stand_task(self, stand_id: str, reason: str):
    print(f"[WORKER] Freezing stand_id={stand_id}, reason: {reason}")
    frozen_until = datetime.now(timezone.utc) + timedelta(hours=settings.FREEZE_DURATION_HOURS)

    from app.core.database import SessionLocal
    from app.core.models import Stand, StandStatusEnum

    with SessionLocal() as db:
        stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
        if stand:
            stand.status = StandStatusEnum.FREEZE
            stand.frozen_until = frozen_until
            db.commit()

    return {"stand_id": stand_id, "status": "FREEZE", "frozen_until": frozen_until.isoformat()}


@celery_app.task(bind=True, max_retries=3)
def cleanup_stand_task(self, stand_id: str):
    print(f"[WORKER] Cleaning stand_id={stand_id}")
    self.update_state(state="CLEANING", meta={"progress": 10, "message": "Удаление ВМ из кластера..."})

    try:
        os_client = OpenStackClient()
        os_client.cleanup_lab3_stand(stand_id)
    except Exception as e:
        print(f"[WORKER] OpenStack cleanup failed: {e}")

    self.update_state(state="CLEANING", meta={"progress": 90, "message": "Освобождение стенда..."})

    from app.core.database import SessionLocal
    from app.core.models import Stand, StandStatusEnum

    with SessionLocal() as db:
        stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
        if stand:
            stand.status = StandStatusEnum.FREE
            stand.user_id = None
            stand.ip_address = None
            stand.private_key = None
            stand.vm_details = None
            stand.expires_at = None
            stand.frozen_until = None
            db.commit()

    return {"stand_id": stand_id, "status": "FREE"}
