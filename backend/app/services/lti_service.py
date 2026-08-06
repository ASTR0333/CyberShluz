"""
Ядро LTI 1.3 Tool (Этап 4).

Реализует со стороны оркестратора (Tool):
  - OIDC third-party initiation (login) -> redirect на платформу;
  - валидацию id_token (LtiResourceLinkRequest) от Moodle;
  - AGS (Assignment & Grade Services): получение OAuth2-токена по
    client_credentials (подпись client_assertion ключом Tool) и отправку
    оценки (score) в lineitem активности Moodle.

Без сторонних LTI-фреймворков: только PyJWT(RS256) + httpx, чтобы поток был
прозрачным и аудируемым.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import jwt

from app.core.config import settings
from app.core.lti import keys
from app.core.lti.platform import PlatformConfig, get_jwk_client, get_platform

logger = logging.getLogger(__name__)

 
CLAIM_MESSAGE_TYPE = "https://purl.imsglobal.org/spec/lti/claim/message_type"
CLAIM_VERSION = "https://purl.imsglobal.org/spec/lti/claim/version"
CLAIM_DEPLOYMENT_ID = "https://purl.imsglobal.org/spec/lti/claim/deployment_id"
CLAIM_ROLES = "https://purl.imsglobal.org/spec/lti/claim/roles"
CLAIM_CONTEXT = "https://purl.imsglobal.org/spec/lti/claim/context"
CLAIM_RESOURCE_LINK = "https://purl.imsglobal.org/spec/lti/claim/resource_link"
CLAIM_AGS = "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"

AGS_SCOPE_LINEITEM = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
AGS_SCOPE_SCORE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"
AGS_SCOPE_RESULT = "https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"

STATE_TTL_SECONDS = 600
ROLE_INSTRUCTOR = "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
ROLE_ADMIN = "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Administrator"


class LtiError(Exception):
    """Ошибка обработки LTI-запроса (отдаём 400/401 на уровне роутера)."""


@dataclass
class AgsEndpoint:
    lineitem: str | None
    lineitems: str | None
    scopes: list[str]


@dataclass
class LtiLaunch:
    sub: str
    name: str
    email: str
    roles: list[str]
    context_id: str
    context_title: str
    resource_link_id: str
    deployment_id: str
    ags: AgsEndpoint

    @property
    def is_instructor(self) -> bool:
        return any(r in (ROLE_INSTRUCTOR, ROLE_ADMIN) for r in self.roles)


 
 
 
def build_login_redirect(
    iss: str,
    login_hint: str,
    target_link_uri: str,
    lti_message_hint: str | None,
    client_id: str | None,
) -> str:
    """
    Возвращает URL для редиректа браузера на auth-эндпоинт платформы.
    state и nonce подписываем своим секретом (stateless) — на launch сверяем.
    """
    platform = get_platform()
    if iss.rstrip("/") != platform.issuer.rstrip("/"):
        raise LtiError(f"Неизвестный issuer: {iss}")

    nonce = uuid.uuid4().hex
    state = jwt.encode(
        {
            "nonce": nonce,
            "target_link_uri": target_link_uri,
            "exp": int(time.time()) + STATE_TTL_SECONDS,
        },
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )

    params = {
        "scope": "openid",
        "response_type": "id_token",
        "response_mode": "form_post",
        "prompt": "none",
        "client_id": client_id or platform.client_id,
        "redirect_uri": target_link_uri,
        "login_hint": login_hint,
        "state": state,
        "nonce": nonce,
    }
    if lti_message_hint:
        params["lti_message_hint"] = lti_message_hint

    return f"{platform.auth_login_url}?{urlencode(params)}"


def _validate_state(state: str) -> str:
    try:
        decoded = jwt.decode(state, settings.JWT_SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise LtiError(f"Невалидный state: {exc}") from exc
    return decoded["nonce"]


 
 
 
def validate_launch(id_token: str, state: str) -> LtiLaunch:
    platform = get_platform()
    expected_nonce = _validate_state(state)

    try:
        signing_key = get_jwk_client().get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=platform.client_id,
            issuer=platform.issuer,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise LtiError(f"Подпись/claims id_token невалидны: {exc}") from exc

    if claims.get("nonce") != expected_nonce:
        raise LtiError("nonce не совпадает (возможна replay-атака)")

    if claims.get(CLAIM_MESSAGE_TYPE) != "LtiResourceLinkRequest":
        raise LtiError(f"Неподдерживаемый message_type: {claims.get(CLAIM_MESSAGE_TYPE)}")
    if claims.get(CLAIM_VERSION) != "1.3.0":
        raise LtiError(f"Неподдерживаемая версия LTI: {claims.get(CLAIM_VERSION)}")

    deployment_id = str(claims.get(CLAIM_DEPLOYMENT_ID, ""))
    if platform.deployment_id and deployment_id != platform.deployment_id:
        raise LtiError(f"Неизвестный deployment_id: {deployment_id}")

    ags_claim: dict[str, Any] = claims.get(CLAIM_AGS) or {}
    ags = AgsEndpoint(
        lineitem=ags_claim.get("lineitem"),
        lineitems=ags_claim.get("lineitems"),
        scopes=ags_claim.get("scope", []),
    )

    context = claims.get(CLAIM_CONTEXT) or {}
    resource_link = claims.get(CLAIM_RESOURCE_LINK) or {}

    return LtiLaunch(
        sub=str(claims["sub"]),
        name=claims.get("name", ""),
        email=claims.get("email", ""),
        roles=claims.get(CLAIM_ROLES, []),
        context_id=str(context.get("id", "")),
        context_title=context.get("title", ""),
        resource_link_id=str(resource_link.get("id", "")),
        deployment_id=deployment_id,
        ags=ags,
    )


 
 
 
def _client_assertion(platform: PlatformConfig) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": platform.client_id,
            "sub": platform.client_id,
            "aud": platform.auth_token_url,
            "iat": now,
            "exp": now + 300,
            "jti": uuid.uuid4().hex,
        },
        keys.get_private_key_pem(),
        algorithm="RS256",
        headers={"kid": settings.LTI_KEY_ID},
    )


def get_ags_access_token(scopes: list[str]) -> str:
    """OAuth2 client_credentials grant (LTI Advantage Security Framework)."""
    platform = get_platform()
    data = {
        "grant_type": "client_credentials",
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": _client_assertion(platform),
        "scope": " ".join(scopes),
    }
    resp = httpx.post(platform.auth_token_url, data=data, timeout=20.0)
    if resp.status_code != 200:
        raise LtiError(f"AGS token error {resp.status_code}: {resp.text[:300]}")
    return resp.json()["access_token"]


def _scores_url(lineitem_url: str) -> str:
    """Вставляет /scores в путь lineitem перед query-строкой (как требует AGS)."""
    parts = urlsplit(lineitem_url)
    new_path = parts.path.rstrip("/") + "/scores"
    return urlunsplit((parts.scheme, parts.netloc, new_path, parts.query, parts.fragment))


def submit_score(
    lineitem_url: str,
    user_sub: str,
    score_given: float,
    score_maximum: float,
    comment: str = "",
) -> None:
    """Отправляет оценку студента в lineitem активности Moodle (AGS Score)."""
    token = get_ags_access_token([AGS_SCOPE_SCORE])
    payload = {
        "userId": user_sub,
        "scoreGiven": score_given,
        "scoreMaximum": score_maximum,
        "comment": comment,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "activityProgress": "Completed",
        "gradingProgress": "FullyGraded",
    }
    url = _scores_url(lineitem_url)
    resp = httpx.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/vnd.ims.lis.v1.score+json",
        },
        timeout=20.0,
    )
    if resp.status_code not in (200, 201, 202, 204):
        raise LtiError(f"AGS score error {resp.status_code}: {resp.text[:300]}")
    logger.info("[LTI/AGS] Оценка %s/%s отправлена для userId=%s", score_given, score_maximum, user_sub)
