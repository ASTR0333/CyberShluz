import json
import logging
import os
import tempfile

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.models import Stand, StandStatusEnum
from app.core.security import assert_stand_owner_or_teacher, require_student
from app.services.checker_service import CheckerService
from app.tasks.deploy import cleanup_stand_task
from app.core.config import settings

RESULTS_DB: dict[str, dict] = {}

router = APIRouter()
logger = logging.getLogger(__name__)

MANUAL_CHECKS = {
    "w_dc_services": "На W-DC запущены Storage Node Service, Catalog Browser Service и Elasticsearch",
    "w_dc_registered": "w-dc.cyberprotect.test отображается в списке узлов хранения",
    "repositories_present": "Хранилища RepoW и RepoL созданы и отображаются в веб-консоли",
}


def push_lti_grade(stand_id: str, score_given: float = 100.0) -> None:
    """
    Возврат оценки в Moodle через LTI AGS после успешной проверки ЛР.
    Безопасно no-op, если стенд не был запущен из Moodle (нет lti_context).
    Ошибки логируются, но не ломают основной поток проверки.
    """
    from app.services import lti_service

    try:
        with SessionLocal() as db:
            stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
            if not stand or not stand.lti_context:
                return
            ctx = json.loads(stand.lti_context)

        lineitem = ctx.get("lineitem")
        sub = ctx.get("sub")
        if not lineitem or not sub:
            logger.info("[LTI/AGS] Стенд %s без lineitem/sub — оценку не отправляем", stand_id)
            return

        lti_service.submit_score(
            lineitem_url=lineitem,
            user_sub=sub,
            score_given=score_given,
            score_maximum=float(ctx.get("score_maximum", 100.0)),
            comment="Лабораторная работа пройдена: проверка конфигурации стенда успешна.",
        )
        logger.info("[LTI/AGS] Оценка %s отправлена в Moodle для стенда %s", score_given, stand_id)
    except Exception:
        logger.exception("[LTI/AGS] Не удалось отправить оценку для стенда %s", stand_id)


class CheckRequest(BaseModel):
    lab_template: str = Field(default="lab03_cyber", pattern=r"^[a-z0-9_]+$")
    manual_confirmations: list[str] = Field(default_factory=list)


@router.post(
    "/check/{stand_id}",
    status_code=202,
    summary="Запуск проверки конфигурации стенда",
    description="Запускает Ansible-проверку конфигурации стенда по SSH.",
)
async def start_check(
    stand_id: int,
    request: CheckRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(require_student),
):
    if request.lab_template != "lab03_cyber":
        raise HTTPException(status_code=422, detail="Поддерживается только шаблон lab03_cyber")

    stand = db.query(Stand).filter(Stand.id == stand_id).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")
    assert_stand_owner_or_teacher(user, stand.user_id)

    if not stand.vm_details:
        raise HTTPException(status_code=400, detail="Стенд еще не развернут (нет данных о ВМ)")

    try:
        vm_results = json.loads(stand.vm_details)
        lms_ip = vm_results.get("L-MS", {}).get("floating_ip") or stand.ip_address
        if not lms_ip:
            raise ValueError("У L-MS нет Floating IP")

        stand_hosts = {"L-MS": {"address": lms_ip}}
        for role in ("L-NFS", "L-PGSQL"):
            vm = vm_results.get(role, {})
            address = vm.get("ip") or vm.get("expected_ip")
            if not address:
                raise ValueError(f"В топологии отсутствует адрес {role}")
            stand_hosts[role] = {"address": address, "proxy_jump": lms_ip}
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        logger.error(f"Error parsing vm_details for stand {stand_id}: {e}")
        raise HTTPException(status_code=400, detail=f"Ошибка топологии для проверки: {e}")

    confirmations = set(request.manual_confirmations)
    unknown_confirmations = confirmations - set(MANUAL_CHECKS)
    if unknown_confirmations:
        raise HTTPException(
            status_code=422,
            detail="Неизвестные ручные подтверждения: " + ", ".join(sorted(unknown_confirmations)),
        )
    missing_manual = [key for key in MANUAL_CHECKS if key not in confirmations]

    ssh_key_content = stand.private_key
    stand_id_str = str(stand_id)

    RESULTS_DB[stand_id_str] = {
        "status": "CHECKING",
        "log": "Проверка запущена. Выполняются тесты на L-MS и L-NFS...",
        "details": {}
    }
    stand.last_check_result = json.dumps(RESULTS_DB[stand_id_str], ensure_ascii=False)
    db.commit()

    if not ssh_key_content or "MOCK" in ssh_key_content or "SIMULATED" in ssh_key_content:
        if not (settings.APP_ENV == "development" and settings.ENABLE_MOCK_CHECKS):
            result = {
                "status": "ERROR",
                "log": "Автоматическая проверка недоступна: у стенда нет рабочего SSH-ключа.",
                "details": {"ssh_accessible": False},
            }
            RESULTS_DB[stand_id_str] = result
            stand.last_check_result = json.dumps(result, ensure_ascii=False)
            db.commit()
            return {
                "stand_id": stand_id_str,
                "check_task_id": stand_id_str,
                "status": "ERROR",
                "message": result["log"],
            }

         
        async def mock_check():
            import asyncio
            await asyncio.sleep(2)
            status_value = "REVIEW_REQUIRED" if missing_manual else "PASSED"
            RESULTS_DB[stand_id_str] = {
                "status": status_value,
                "log": (
                    "✅ [L-MS] Проверка доступности (Порт 9877) — OK\n"
                    "✅ [L-NFS] Проверка Hostname (cyberprotect.test) — OK\n"
                    "✅ [L-NFS] Проверка модуля snapapi — OK\n"
                    "✅ [L-NFS] Проверка портов Firewall (7780, 9876...) — OK\n"
                    "✅ Все проверки пройдены успешно."
                ),
                "details": {
                    "ssh_accessible": True,
                    "port_9877_open": True,
                    "snapapi_loaded": True,
                    "acronis_active": True,
                    "manual_confirmed": not missing_manual,
                }
            }
            with SessionLocal() as db_session:
                db_stand = db_session.query(Stand).filter(Stand.id == stand_id).first()
                if db_stand:
                    db_stand.last_check_result = json.dumps(RESULTS_DB[stand_id_str], ensure_ascii=False)
                    db_session.commit()
            if not missing_manual:
                push_lti_grade(stand_id_str, score_given=100.0)
        background_tasks.add_task(mock_check)
    else:
        checker = CheckerService.from_env()

        async def run_check_task():
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=True) as tmp_key:
                tmp_key.write(ssh_key_content)
                tmp_key.flush()
                os.chmod(tmp_key.name, 0o600)
                try:
                    result = await checker.check_stand(
                        stand_id=stand_id_str,
                        stand_hosts=stand_hosts,
                        ssh_user=settings.VM_ADMIN_USER,
                        ssh_key_path=tmp_key.name,
                        lab_template=request.lab_template,
                    )

                    if result.status == "PASSED" and missing_manual:
                        result.status = "REVIEW_REQUIRED"
                        result.details["manual_confirmed"] = False
                        checklist = "\n".join(f"  - {MANUAL_CHECKS[key]}" for key in missing_manual)
                        result.log += (
                            "\n\nАвтоматические проверки пройдены. Для завершения подтвердите вручную:\n"
                            + checklist
                        )
                    elif result.status == "PASSED":
                        result.details["manual_confirmed"] = True

                    check_data = {
                        "status": result.status,
                        "log": result.log,
                        "details": result.details,
                    }
                    RESULTS_DB[stand_id_str] = check_data

                    with SessionLocal() as db_session:
                        db_stand = db_session.query(Stand).filter(Stand.id == stand_id).first()
                        if db_stand:
                            db_stand.last_check_result = json.dumps(check_data, ensure_ascii=False)
                            if result.status == "PASSED":
                                 
                                db_stand.status = StandStatusEnum.CLEANING
                                db_session.commit()
                                logger.info("Stand %s PASSED. Triggering cleanup.", stand_id)
                                try:
                                    cleanup_stand_task.delay(stand_id_str)
                                except Exception:
                                    db_stand.status = StandStatusEnum.READY
                                    db_session.commit()
                                    raise
                                push_lti_grade(stand_id_str, score_given=100.0)
                            else:
                                db_session.commit()
                except Exception as e:
                    logger.exception("Error during check for stand %s", stand_id)
                    RESULTS_DB[stand_id_str] = {
                        "status": "ERROR",
                        "log": f"Сбой проверки: {e}",
                        "details": {},
                    }
                    with SessionLocal() as db_session:
                        db_stand = db_session.query(Stand).filter(Stand.id == stand_id).first()
                        if db_stand:
                            db_stand.last_check_result = json.dumps(
                                RESULTS_DB[stand_id_str],
                                ensure_ascii=False,
                            )
                            db_session.commit()

        background_tasks.add_task(run_check_task)

    return {
        "stand_id": stand_id_str,
        "check_task_id": stand_id_str,
        "status": "CHECKING",
        "message": "Проверка запущена"
    }


@router.get(
    "/check/{stand_id}/result",
    summary="Получить результат проверки",
)
async def get_check_result(stand_id: int, db: Session = Depends(get_db), user=Depends(require_student)):
    stand = db.query(Stand).filter(Stand.id == stand_id).first()
    if stand:
        assert_stand_owner_or_teacher(user, stand.user_id)
    result = RESULTS_DB.get(str(stand_id))
    if not result and stand and stand.last_check_result:
        try:
            result = json.loads(stand.last_check_result)
        except json.JSONDecodeError:
            result = None
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Результатов проверки пока нет."
        )
    return result
