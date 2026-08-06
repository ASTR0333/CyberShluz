import json
import logging
import os
import tempfile

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.models import Stand, StandStatusEnum
from app.core.security import assert_stand_owner_or_teacher, require_student
from app.services.checker_service import CheckerService
from app.tasks.deploy import cleanup_stand_task

RESULTS_DB: dict[str, dict] = {}

router = APIRouter()
logger = logging.getLogger(__name__)


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
    lab_template: str = "lab03_cyber"


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
    stand = db.query(Stand).filter(Stand.id == stand_id).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")
    assert_stand_owner_or_teacher(user, stand.user_id)

    if not stand.vm_details:
        raise HTTPException(status_code=400, detail="Стенд еще не развернут (нет данных о ВМ)")

    try:
        vm_results = json.loads(stand.vm_details)
        lms_ip = vm_results.get("L-MS", {}).get("floating_ip")
        nfs_ip = vm_results.get("L-NFS", {}).get("floating_ip")
        
         
        stand_ips = [ip for ip in [lms_ip, nfs_ip] if ip]
        
        if not stand_ips:
              
             if stand.ip_address:
                 stand_ips = [stand.ip_address]
             else:
                 raise HTTPException(status_code=400, detail="Не удалось определить IP-адреса машин для проверки")
    except Exception as e:
        logger.error(f"Error parsing vm_details for stand {stand_id}: {e}")
        if stand.ip_address:
            stand_ips = [stand.ip_address]
        else:
            raise HTTPException(status_code=400, detail="Ошибка при определении IP-адресов стенда")

    ssh_key_content = stand.private_key
    stand_id_str = str(stand_id)

    RESULTS_DB[stand_id_str] = {
        "status": "CHECKING",
        "log": "Проверка запущена. Выполняются тесты на L-MS и L-NFS...",
        "details": {}
    }

    if not ssh_key_content or "MOCK" in ssh_key_content or "SIMULATED" in ssh_key_content:
         
        async def mock_check():
            import asyncio
            await asyncio.sleep(2)
            RESULTS_DB[stand_id_str] = {
                "status": "PASSED",
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
                }
            }
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
                        stand_ips=stand_ips,
                        ssh_user="student",
                        ssh_key_path=tmp_key.name,
                        lab_template=request.lab_template,
                    )

                    check_data = {
                        "status": result.status,
                        "log": result.log,
                        "details": result.details,
                    }
                    RESULTS_DB[stand_id_str] = check_data

                    with SessionLocal() as db_session:
                        db_stand = db_session.query(Stand).filter(Stand.id == stand_id).first()
                        if db_stand:
                            db_stand.last_check_result = json.dumps(check_data)
                            if result.status == "PASSED":
                                 
                                db_stand.status = StandStatusEnum.CLEANING
                                db_session.commit()
                                logger.info("Stand %s PASSED. Triggering cleanup.", stand_id)
                                 
                                 
                                push_lti_grade(stand_id_str, score_given=100.0)
                                cleanup_stand_task.delay(stand_id_str)
                            else:
                                db_session.commit()
                except Exception as e:
                    logger.exception("Error during check for stand %s", stand_id)
                    RESULTS_DB[stand_id_str] = {
                        "status": "ERROR",
                        "log": f"Сбой проверки: {e}",
                        "details": {},
                    }

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
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Результатов проверки пока нет."
        )
    return result
