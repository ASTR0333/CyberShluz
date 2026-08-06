"""
Конфигурация платформы LTI 1.3 (Moodle) со стороны Tool.

Хранит параметры регистрации External Tool (issuer, client_id, deployment_id,
эндпоинты auth/token/keyset) и кэширующий JWKS-клиент для проверки подписи
id_token, прилетающего от Moodle.
"""
from __future__ import annotations

from dataclasses import dataclass

import jwt

from app.core.config import settings


@dataclass(frozen=True)
class PlatformConfig:
    issuer: str
    client_id: str
    deployment_id: str
    auth_login_url: str
    auth_token_url: str
    keyset_url: str


def get_platform() -> PlatformConfig:
    return PlatformConfig(
        issuer=settings.LTI_ISSUER,
        client_id=settings.LTI_CLIENT_ID,
        deployment_id=settings.LTI_DEPLOYMENT_ID,
        auth_login_url=settings.LTI_AUTH_LOGIN_URL,
        auth_token_url=settings.LTI_AUTH_TOKEN_URL,
        keyset_url=settings.LTI_KEYSET_URL,
    )


_jwk_client: jwt.PyJWKClient | None = None


def get_jwk_client() -> jwt.PyJWKClient:
    """Кэширующий клиент публичных ключей платформы (Moodle certs.php)."""
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = jwt.PyJWKClient(settings.LTI_KEYSET_URL, cache_keys=True)
    return _jwk_client
