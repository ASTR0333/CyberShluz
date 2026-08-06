"""
LTI 1.3 Tool endpoints (Этап 4).

Сквозной сценарий:
  Студент в Moodle жмёт «Выполнить ЛР №3»
    -> Moodle OIDC login  -> GET/POST /lti/login  (редирект обратно на платформу)
    -> Moodle id_token     -> POST   /lti/launch  (валидация, выделение проекта,
                                                    деплой стенда, редирект на UI)
  /lti/jwks — публичный ключ Tool для проверки client_assertion (AGS) платформой.

Возврат оценки (AGS) выполняется асинхронно после прохождения проверки ЛР3
(см. app/api/v1/check.py).
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.lti import keys
from app.core.models import RoleEnum, Stand, StandStatusEnum, User
from app.core.security import UserRole, create_access_token
from app.services import lti_service
from app.services.lti_service import LtiError

logger = logging.getLogger(__name__)
router = APIRouter()

ACTIVE_STATUSES = (
    StandStatusEnum.PENDING,
    StandStatusEnum.DEPLOYING,
    StandStatusEnum.READY,
    StandStatusEnum.FREEZE,
)


def _error_page(message: str, status_code: int = 400) -> HTMLResponse:
    html = (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<title>КиберШлюз — ошибка LTI</title></head>"
        "<body style='font-family:sans-serif;max-width:640px;margin:40px auto;'>"
        "<h2>Не удалось запустить лабораторную работу</h2>"
        f"<p style='color:#b00'>{message}</p>"
        "<p>Вернитесь в Moodle и попробуйте ещё раз. Если проблема повторяется — "
        "обратитесь к преподавателю.</p></body></html>"
    )
    return HTMLResponse(content=html, status_code=status_code)


@router.get("/lti/jwks", summary="JWKS публичного ключа Tool (для AGS)")
def lti_jwks():
    return JSONResponse(content=keys.get_jwks())


@router.api_route(
    "/lti/login",
    methods=["GET", "POST"],
    summary="OIDC third-party initiation (LTI 1.3)",
)
async def lti_login(request: Request):
    params = dict(request.query_params)
    if request.method == "POST":
        form = await request.form()
        params.update({k: v for k, v in form.items()})

    iss = params.get("iss", "")
    login_hint = params.get("login_hint", "")
    target_link_uri = params.get("target_link_uri", "")
    if not (iss and login_hint and target_link_uri):
        return _error_page("Отсутствуют обязательные параметры OIDC (iss/login_hint/target_link_uri).")

    try:
        redirect_url = lti_service.build_login_redirect(
            iss=iss,
            login_hint=login_hint,
            target_link_uri=target_link_uri,
            lti_message_hint=params.get("lti_message_hint"),
            client_id=params.get("client_id"),
        )
    except LtiError as exc:
        return _error_page(str(exc), 401)

    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/lti/launch", summary="LTI 1.3 Resource Link launch → деплой стенда")
async def lti_launch(
    request: Request,
    state: str = Form(""),
    id_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if not (state and id_token):
        return _error_page("Отсутствует state или id_token в launch-запросе.")

    try:
        launch = lti_service.validate_launch(id_token, state)
    except LtiError as exc:
        logger.warning("[LTI] launch отклонён: %s", exc)
        return _error_page(str(exc), 401)

    role_str = UserRole.TEACHER if launch.is_instructor else UserRole.STUDENT
    role_enum = RoleEnum.TEACHER if launch.is_instructor else RoleEnum.STUDENT
    lms_id = f"lti:{launch.sub}"

    ags_context = {
        "sub": launch.sub,
        "issuer": settings.LTI_ISSUER,
        "lineitem": launch.ags.lineitem,
        "lineitems": launch.ags.lineitems,
        "scopes": launch.ags.scopes,
        "resource_link_id": launch.resource_link_id,
        "context_id": launch.context_id,
        "score_maximum": 100.0,
        "lab_id": settings.LTI_GRADE_LAB_ID,
    }

    ags_json = json.dumps(ags_context, ensure_ascii=False)

     
     
     
    user = db.query(User).filter(User.lms_id == lms_id).first()
    if not user:
        user = User(lms_id=lms_id, role=role_enum, lti_context=ags_json)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.lti_context = ags_json

     
     
    stand = (
        db.query(Stand)
        .filter(Stand.user_id == user.id, Stand.status.in_(ACTIVE_STATUSES))
        .first()
    )
    if stand:
        stand.lti_context = ags_json
        db.commit()
        logger.info("[LTI] user=%s -> переиспользован стенд #%s", lms_id, stand.id)
    else:
        db.commit()
        logger.info("[LTI] user=%s -> стенд не создаётся, студент запустит вручную", lms_id)

     
    token = create_access_token(
        data={"sub": lms_id, "role": role_str, "user_id": user.id},
        expires_delta=timedelta(hours=4),
    )

     
    base = settings.LTI_FRONTEND_BASE_URL.rstrip("/")
    path = f"/status/{stand.id}" if stand else "/launch"
    target = f"{base}{path}?lti_token={token}"
    return RedirectResponse(url=target, status_code=302)
