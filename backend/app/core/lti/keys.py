"""
Ключевой материал LTI 1.3 Tool (оркестратор).

Tool подписывает своим приватным RSA-ключом:
  - client_assertion для запроса OAuth2-токена AGS у платформы;
и публикует публичный ключ как JWKS по /api/v1/lti/jwks, чтобы Moodle мог
проверять подпись.

Ключ генерируется один раз и сохраняется на диск (LTI_PRIVATE_KEY_PATH),
чтобы переживать рестарты контейнера.
"""
from __future__ import annotations

import base64
import os
import threading

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import settings

_lock = threading.Lock()
_private_pem: bytes | None = None


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _generate_and_persist(path: str) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(pem)
    os.chmod(path, 0o600)
    return pem


def get_private_key_pem() -> bytes:
    """PEM приватного ключа Tool; генерирует и кэширует при первом обращении."""
    global _private_pem
    if _private_pem is not None:
        return _private_pem
    with _lock:
        if _private_pem is not None:
            return _private_pem
        path = settings.LTI_PRIVATE_KEY_PATH
        if os.path.exists(path):
            with open(path, "rb") as f:
                _private_pem = f.read()
        else:
            _private_pem = _generate_and_persist(path)
        return _private_pem


def _public_key():
    pem = get_private_key_pem()
    return serialization.load_pem_private_key(pem, password=None).public_key()


def get_public_jwk() -> dict:
    """Публичный ключ Tool в формате JWK (RS256)."""
    numbers = _public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": settings.LTI_KEY_ID,
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }


def get_jwks() -> dict:
    return {"keys": [get_public_jwk()]}
