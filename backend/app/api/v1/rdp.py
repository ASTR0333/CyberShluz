"""Issue short-lived, owner-scoped browser RDP sessions for W-DC."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import time
from urllib.parse import quote

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.models import Stand, StandStatusEnum
from app.core.security import assert_stand_owner_or_teacher, require_student
from app.services.rdp_gateway import RDPGatewayError, rdp_tunnel_broker

router = APIRouter()
_RDP_READY_STATUSES = (StandStatusEnum.READY, StandStatusEnum.FREEZE)
_CONNECTION_NAME = "W-DC"


def _guacamole_key() -> bytes:
    try:
        key = bytes.fromhex(settings.GUACAMOLE_JSON_SECRET_KEY)
    except ValueError as exc:
        raise ValueError("GUACAMOLE_JSON_SECRET_KEY должен содержать 32 hex-символа") from exc
    if len(key) != 16:
        raise ValueError("GUACAMOLE_JSON_SECRET_KEY должен содержать 32 hex-символа")
    return key


def encrypt_guacamole_json(payload: dict) -> str:
    """Sign and encrypt JSON exactly as guacamole-auth-json requires."""
    key = _guacamole_key()
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signed = hmac.new(key, plaintext, hashlib.sha256).digest() + plaintext
    padder = padding.PKCS7(128).padder()
    padded = padder.update(signed) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(bytes(16))).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("ascii")


def guacamole_client_identifier(connection_name: str = _CONNECTION_NAME) -> str:
    raw = f"{connection_name}\0c\0json".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _wdc_ip(stand: Stand) -> str:
    try:
        vms = json.loads(stand.vm_details or "{}")
        network = json.loads(stand.network_details or "{}")
        wdc = vms["W-DC"]
        address = ipaddress.ip_address(wdc.get("ip") or wdc["expected_ip"])
        subnet = ipaddress.ip_network(network["cidr"], strict=True)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=409, detail="В топологии стенда нет корректной W-DC") from exc
    if address.version != 4 or address not in subnet:
        raise HTTPException(status_code=409, detail="IP W-DC находится вне сети стенда")
    return str(address)


@router.post("/stand/{stand_id}/rdp-session", summary="Открыть W-DC в браузере")
def create_rdp_session(
    stand_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_student),
):
    try:
        numeric_id = int(stand_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный идентификатор стенда") from exc

    stand = db.query(Stand).filter(Stand.id == numeric_id).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")
    assert_stand_owner_or_teacher(user, stand.user_id)
    if stand.status not in _RDP_READY_STATUSES or not stand.ip_address:
        raise HTTPException(status_code=409, detail="Стенд ещё не готов к подключению")
    if not stand.student_private_key:
        raise HTTPException(status_code=409, detail="Для стенда не подготовлен ключ доступа")

    target_ip = _wdc_ip(stand)
    tunnel = None
    try:
        tunnel = rdp_tunnel_broker.open(stand.ip_address, stand.student_private_key, target_ip)
        ttl = max(30, min(settings.RDP_SESSION_TOKEN_TTL_SECONDS, 300))
        expires_ms = int((time.time() + ttl) * 1000)
        payload = {
            "username": f"cybershluz-{user.get('user_id', 'user')}-stand-{stand.id}",
            "expires": expires_ms,
            "singleUse": True,
            "connections": {
                _CONNECTION_NAME: {
                    "protocol": "rdp",
                    "parameters": {
                        "hostname": settings.RDP_TUNNEL_HOST,
                        "port": str(tunnel.port),
                        "username": settings.WDC_RDP_USERNAME,
                        "password": settings.WDC_RDP_PASSWORD,
                        "domain": settings.WDC_RDP_DOMAIN,
                        "security": "any",
                        "ignore-cert": "true",
                        "disable-audio": "true",
                        "resize-method": "display-update",
                    },
                }
            },
        }
        encrypted = encrypt_guacamole_json(payload)
    except (RDPGatewayError, ValueError) as exc:
        if tunnel is not None:
            tunnel.close()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    client_id = guacamole_client_identifier()
    return {
        "launch_url": f"/rdp/#/client/{client_id}?data={quote(encrypted, safe='')}",
        "expires_at": expires_ms,
    }
