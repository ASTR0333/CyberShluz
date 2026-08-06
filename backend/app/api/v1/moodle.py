 
import hmac
import hashlib
import json
import time
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, status, Request
from pydantic import BaseModel
import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class MoodlePayload(BaseModel):
    user_id: str
    user_name: str
    course_id: str
    role: str
    lab_template: str


class LaunchResponse(BaseModel):
    access_token: str
    token_type: str
    project_id: str
    domain_id: str


def verify_moodle_signature(payload_bytes: bytes, signature: str) -> bool:
    expected_mac = hmac.new(
        settings.MOODLE_SHARED_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_mac, signature)


def create_jwt_token(data: dict, expires_delta_hours: int = 4) -> str:
    to_encode = data.copy()
    expire = time.time() + (expires_delta_hours * 3600)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@router.post(
    "/moodle/launch",
    response_model=LaunchResponse,
    status_code=status.HTTP_200_OK,
    summary="LTI / REST шлюз интеграции для LMS Moodle",
    description=(
        "Шлюз бесшовной аутентификации Moodle → оркестратор.\n\n"
        "**Логика:**\n"
        "1. Проверка подлинности запроса (HMAC SHA-256, заголовок `X-Moodle-Signature`).\n"
        "2. Маппинг course_id / user_id в изолированный домен/проект КИ.\n"
        "3. Выдача JWT-сессии для дальнейших вызовов API."
    ),
)
async def moodle_launch_gateway(
    request: Request,
    x_moodle_signature: Optional[str] = Header(
        None,
        description="HMAC SHA-256 подпись тела запроса (hex)",
    ),
):
    if not x_moodle_signature:
        logger.warning("[MOODLE] Запрос отклонён: отсутствует заголовок подписи")
        raise HTTPException(status_code=401, detail="X-Moodle-Signature header is missing")

    body_bytes = await request.body()

    if not verify_moodle_signature(body_bytes, x_moodle_signature):
        logger.error("[MOODLE] Запрос отклонён: невалидная HMAC подпись")
        raise HTTPException(status_code=403, detail="Invalid Moodle HMAC signature")

    try:
        data = json.loads(body_bytes)
        payload = MoodlePayload(**data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON parsing error: {e}")

    domain_id = f"domain_{payload.course_id}"
    project_id = f"project_{payload.course_id}_{payload.user_id}"

    logger.info("[MOODLE] course=%s -> domain=%s", payload.course_id, domain_id)
    logger.info("[MOODLE] user=%s -> project=%s", payload.user_id, project_id)

    jwt_payload = {
        "sub": payload.user_id,
        "name": payload.user_name,
        "role": payload.role,
        "domain_id": domain_id,
        "project_id": project_id,
        "lab_template": payload.lab_template,
    }

    token = create_jwt_token(jwt_payload)

    return LaunchResponse(
        access_token=token,
        token_type="bearer",
        project_id=project_id,
        domain_id=domain_id,
    )
