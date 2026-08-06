 
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas.contracts import DeployRequest, DeploymentOptionsResponse, DeployResponse
from app.tasks.deploy import deploy_stand_task
from app.core.pool_manager import PoolManager
from app.core.database import get_db
from app.core.models import RoleEnum, Stand, StandStatusEnum, User
from app.core.openstack_client import OpenStackClient, CapacityExceededException
from app.core.config import settings
from app.core.topology import default_lab3_config
from app.core.security import UserRole, require_student

 
logger = logging.getLogger("admin_platform_logs")
router = APIRouter()


@router.get(
    "/deployment-options",
    response_model=DeploymentOptionsResponse,
    summary="Получить параметры для интерактивного развёртывания",
)
async def deployment_options(user=Depends(require_student)):
    del user
    default = default_lab3_config(settings.OS_NETWORK_NAME or "public")
    try:
        catalog = OpenStackClient().get_deployment_catalog()
        return DeploymentOptionsResponse(default=default, **catalog)
    except Exception as exc:
        logger.warning("OpenStack catalog is unavailable: %s", exc)
        return DeploymentOptionsResponse(
            default=default,
            images=sorted({vm.image for vm in default.vms}),
            flavors=sorted({vm.flavor for vm in default.vms}),
            external_networks=[default.network.external_network],
            catalog_error="Каталог OpenStack недоступен; показаны значения из методички.",
        )

@router.post(
    "/deploy",
    response_model=DeployResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запрос на выделение и асинхронное развертывание стенда",
    description=(
        "Асинхронный эндпоинт оркестрации для резервирования облачных ресурсов.\n\n"
        "**Логика:**\n"
        "1. Предиктивный контроль емкости (Nova Limits) — если утилизация + требуемые ресурсы > 90%, возвращает 423 Locked.\n"
        "2. Забирает свободный проект из пула с атомарной блокировкой строки (SELECT FOR UPDATE) и переводит в DEPLOYING.\n"
        "3. Передает задачу Celery для нативного деплоя топологии через OpenStack API."
    ),
)
async def deploy(
    request: DeployRequest,
    db: Session = Depends(get_db),
    user=Depends(require_student),
):
     
     
    auth_username = user.get("sub")
    auth_role = user.get("role")
    auth_user_id = int(user.get("user_id", 0))
    request.user_id = auth_username
    request.role = auth_role
    deployment = request.deployment or default_lab3_config(settings.OS_NETWORK_NAME or "public")

     
    if auth_role == UserRole.STUDENT:
        ACTIVE_STATUSES = (
            StandStatusEnum.PENDING,
            StandStatusEnum.DEPLOYING,
            StandStatusEnum.READY,
            StandStatusEnum.FREEZE,
        )
        active = (
            db.query(Stand)
            .filter(Stand.user_id == auth_user_id, Stand.status.in_(ACTIVE_STATUSES))
            .first()
        )
        if active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"У вас уже есть активный стенд #{active.id} "
                    f"({active.status.value}). Завершите его, прежде чем запускать новый."
                ),
            )

     
     
     
    os_client = OpenStackClient()
    try:
        required_vcpus = os_client.required_vcpus(deployment)
        utilization = os_client.check_capacity(required_vcpus=required_vcpus)
        threshold = getattr(settings, "MAX_CLUSTER_UTILIZATION", 0.90)

        if utilization > threshold:
            logger.error(
                f"[ADMIN_ALERT] ЗАПРОС НА ДЕПЛОЙ ОТКЛОНЕН | Пользователь: {request.user_id} "
                f"| Текущая утилизация: {utilization*100:.1f}% | Лимит: {threshold*100:.1f}%"
            )
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Кластер перегружен ({utilization*100:.1f}%). Попробуйте позже."
            )
    except CapacityExceededException as exc:
        logger.error("Nova capacity API is unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось проверить квоту OpenStack. Развёртывание не запущено.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("OpenStack validation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Не удалось проверить ресурсы OpenStack: {exc}",
        )

     
    pool_manager = PoolManager(db)
    role_enum = RoleEnum.STUDENT if request.role == "student" else RoleEnum.TEACHER
    
     
    stand = pool_manager.allocate_stand(lms_user_id=request.user_id, role=role_enum)

    if not stand:
         
        logger.warning(
            f"[ADMIN_POOL_WARNING] Отказ в выделении: Пул свободных проектов БД исчерпан "
            f"| Пользователь ID: {request.user_id} | Назначен статус: 503 Service Unavailable"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Все изолированные проекты пула сейчас заняты. Пожалуйста, подождите освобождения стендов."
        )

    stand_id_str = str(stand.id)

     
     
     
    owner = db.query(User).filter(User.lms_id == request.user_id).first()
    if owner and owner.lti_context:
        stand.lti_context = owner.lti_context
        db.commit()

     
    try:
        deploy_stand_task.apply_async(
            args=[
                stand_id_str,
                request.user_id,
                request.lab_id,
                request.role,
                deployment.model_dump(mode="json"),
            ],
            task_id=stand_id_str,
        )
    except Exception as exc:
        logger.exception("Failed to enqueue deployment for stand %s", stand_id_str)
        stand.status = StandStatusEnum.FREE
        stand.user_id = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Очередь развёртывания недоступна: {exc}",
        )

    return DeployResponse(
        stand_id=stand_id_str,
        project_id=f"project_{stand.id}",
        status="DEPLOYING",
        message="Проект успешно зарезервирован СУБД. Запущен процесс развертывания инфраструктуры в OpenStack."
    )
