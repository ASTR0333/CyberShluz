import json
from app.celery_app import celery_app
from datetime import datetime, timedelta, timezone
from app.core.openstack_client import (
    CapacityExceededException,
    OpenStackClient,
    SSHBootstrapError,
)
from app.core.config import settings
from app.core.topology import DeploymentConfig, default_lab3_config


@celery_app.task(bind=True, max_retries=2)
def deploy_stand_task(
    self,
    stand_id: str,
    user_id: str,
    lab_id: int,
    role: str = "student",
    deployment_config: dict | None = None,
    project_ref: str | None = None,
):
    from app.core.database import SessionLocal
    from app.core.models import Stand, StandStatusEnum

    print(f"[WORKER] Starting deployment for stand_id={stand_id}, user={user_id}, lab={lab_id}")

    saved_admin_key = None
    saved_student_key = None
    with SessionLocal() as db:
        stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
        if stand:
            saved_admin_key = stand.private_key
            saved_student_key = stand.student_private_key
            stand.status = StandStatusEnum.DEPLOYING
            db.commit()

    def progress_cb(pct, msg):
        self.update_state(state="DEPLOYING", meta={"progress": pct, "message": msg})

    try:
        progress_cb(5, "Подключение к Кибер Инфраструктуре...")
        os_client = OpenStackClient(project_ref=project_ref)
        deployment = (
            DeploymentConfig.model_validate(deployment_config)
            if deployment_config
            else default_lab3_config(settings.OS_NETWORK_NAME or "public")
        )

        admin_key_name = f"key-stand{stand_id}-admin"
        student_key_name = f"key-stand{stand_id}-student"
        progress_cb(10, "Генерация SSH-ключей администратора и студента...")
        private_key = os_client.create_keypair(
            admin_key_name,
            private_key=saved_admin_key,
        )
        # Persist each private key before any VM is created. A Celery retry must
        # reconcile the OpenStack keypair with this key instead of rotating it.
        with SessionLocal() as key_db:
            key_stand = key_db.query(Stand).filter(Stand.id == int(stand_id)).first()
            if key_stand:
                key_stand.private_key = private_key
                key_db.commit()

        student_private_key = os_client.create_keypair(
            student_key_name,
            private_key=saved_student_key,
        )
        with SessionLocal() as key_db:
            key_stand = key_db.query(Stand).filter(Stand.id == int(stand_id)).first()
            if key_stand:
                key_stand.student_private_key = student_private_key
                key_db.commit()

        progress_cb(20, "Проверка ёмкости кластера...")
        required_vcpus = os_client.required_vcpus(deployment)
        utilization = os_client.check_capacity(required_vcpus=required_vcpus)
        if utilization > settings.MAX_CLUSTER_UTILIZATION:
            raise CapacityExceededException(
                f"Кластер перегружен ({utilization*100:.1f}%)"
            )

        enabled_count = len(deployment.enabled_topology())
        progress_cb(30, f"Развёртывание топологии Лаб. №3 ({enabled_count} ВМ)...")

        def resource_cb(vm_results, network_details):
            # Persist partial progress. A refresh, worker retry or Nova error no
            # longer makes already-created instances disappear from the UI.
            with SessionLocal() as resource_db:
                resource_stand = (
                    resource_db.query(Stand)
                    .filter(Stand.id == int(stand_id))
                    .first()
                )
                if resource_stand:
                    resource_stand.vm_details = json.dumps(vm_results, default=str)
                    resource_stand.network_details = json.dumps(network_details, default=str)
                    resource_db.commit()

        vm_results = os_client.deploy_lab3_stand(
            stand_id,
            admin_key_name,
            student_key_name,
            private_key,
            student_private_key,
            deployment=deployment,
            progress_cb=progress_cb,
            resource_cb=resource_cb,
        )
         
        net_details = vm_results.pop("__network__", None)

        lms = vm_results.get("L-MS", {})
        access_ip = lms.get("floating_ip")
        if not access_ip:
            raise CapacityExceededException("Не удалось получить публичный IP адрес (возможно, исчерпан лимит)")

        active_count = sum(1 for v in vm_results.values() if v.get("status") == "ACTIVE")
        total_count = len(vm_results)
        if active_count != total_count:
            failed_roles = [role for role, vm in vm_results.items() if vm.get("status") != "ACTIVE"]
            raise RuntimeError("Не все ВМ перешли в ACTIVE: " + ", ".join(failed_roles))
        ssh_bootstrapped = vm_results.get("L-MS", {}).get("ssh_bootstrapped", True)

        with SessionLocal() as db:
            stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
            if stand:
                stand.ip_address = access_ip
                stand.private_key = private_key
                stand.student_private_key = student_private_key
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

    except SSHBootstrapError as exc:
        print(f"[WORKER] Secure SSH bootstrap failed: {exc}")
        # The bootstrap function already waits for the VM to become reachable.
        # Replaying the entire OpenStack deployment cannot repair invalid image
        # credentials and used to rotate keys for already-created instances.
        self.update_state(state="FAILURE", meta={"error": str(exc)})
        raise

    except CapacityExceededException as ce:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=ce, countdown=180)
        self.update_state(state="FAILURE", meta={"error": str(ce)})
        raise

    except Exception as exc:
        print(f"[WORKER] Deploy failed: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)
        self.update_state(state="FAILURE", meta={"error": str(exc)})
        raise


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
        from app.core.database import SessionLocal
        from app.core.models import Stand

        with SessionLocal() as lookup_db:
            lookup_stand = lookup_db.query(Stand).filter(Stand.id == int(stand_id)).first()
            project_ref = (
                lookup_stand.project.openstack_project_id
                if lookup_stand and lookup_stand.project
                else None
            )
        os_client = OpenStackClient(project_ref=project_ref)
        os_client.cleanup_lab3_stand(stand_id)
    except Exception as e:
        print(f"[WORKER] OpenStack cleanup failed: {e}")
        raise self.retry(exc=e, countdown=60)

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
            stand.student_private_key = None
            stand.vm_details = None
            stand.network_details = None
            stand.last_check_result = None
            stand.lti_context = None
            stand.expires_at = None
            stand.frozen_until = None
            db.commit()

    return {"stand_id": stand_id, "status": "FREE"}
