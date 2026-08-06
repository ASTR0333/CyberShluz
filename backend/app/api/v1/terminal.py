"""
Веб-терминал к стенду (WebSocket → SSH прокси).

Студент открывает интерактивную SSH-сессию к публичному IP своего стенда прямо
из браузера (xterm.js на фронте). Бэкенд проксирует поток: байты из WebSocket →
в SSH-канал и обратно. Бэкенд использует отдельный ключ непривилегированной
учётной записи student; парольная аутентификация не используется.

Авторизация: JWT передаётся query-параметром `token` (браузерный WebSocket не
умеет слать заголовок Authorization). Студент может открыть только свой стенд,
преподаватель/админ — любой.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging

import jwt
import paramiko
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.models import Stand, StandStatusEnum
from app.core.security import ALGORITHM, SECRET_KEY, UserRole

logger = logging.getLogger(__name__)
router = APIRouter()

_READY_STATUSES = (StandStatusEnum.READY, StandStatusEnum.FREEZE)


def _resolve_stand(stand_id: str, token: str):
    """Возвращает (ip, error). error не None — повод закрыть сокет с сообщением."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None, "Недействительный или истёкший токен."

    db = SessionLocal()
    try:
        try:
            stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
        except ValueError:
            return None, "Некорректный идентификатор стенда."
        if not stand:
            return None, "Стенд не найден."

        role = payload.get("role")
        if role not in (UserRole.TEACHER, UserRole.ADMIN):
            if int(payload.get("user_id", 0)) != int(stand.user_id or 0):
                return None, "Этот стенд принадлежит другому пользователю."

        if stand.status not in _READY_STATUSES or not stand.ip_address:
            return None, "Стенд ещё не готов к подключению."
        return stand.ip_address, None
    finally:
        db.close()


def _load_private_key(private_key: str):
    for key_class in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return key_class.from_private_key(io.StringIO(private_key))
        except Exception:
            continue
    raise ValueError("Unsupported SSH private key format")


def _open_ssh_shell(ip: str, stand_id: str):
    db = SessionLocal()
    try:
        stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
        if not stand or not stand.student_private_key:
            raise ValueError("The stand has no student SSH key")
        private_key = stand.student_private_key
    finally:
        db.close()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())   
    client.connect(
        hostname=ip,
        username=settings.VM_STUDENT_USER,
        pkey=_load_private_key(private_key),
        timeout=12,
        banner_timeout=15,
        auth_timeout=15,
        look_for_keys=False,
        allow_agent=False,
    )
    chan = client.invoke_shell(term="xterm-256color", width=120, height=32)
    chan.settimeout(0.0)
    return client, chan


@router.websocket("/stand/{stand_id}/terminal")
async def stand_terminal(websocket: WebSocket, stand_id: str):
    await websocket.accept()
    token = websocket.query_params.get("token", "")

    ip, error = _resolve_stand(stand_id, token)
    if error:
        await websocket.send_text(f"\r\n\x1b[31m{error}\x1b[0m\r\n")
        await websocket.close()
        return

    loop = asyncio.get_event_loop()
    try:
        client, chan = await loop.run_in_executor(None, _open_ssh_shell, ip, stand_id)
    except Exception as exc:   
        logger.warning("[TERM] SSH к %s не удался: %s", ip, exc)
        await websocket.send_text(
            f"\r\n\x1b[31mНе удалось подключиться к стенду ({ip}): {exc}\x1b[0m\r\n"
        )
        await websocket.close()
        return

    async def ws_to_ssh():
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if isinstance(msg, dict) and msg.get("type") == "resize":
                    chan.resize_pty(width=int(msg["cols"]), height=int(msg["rows"]))
                    continue
            except (ValueError, TypeError, KeyError):
                pass
            chan.send(data)

    async def ssh_to_ws():
        while True:
            await asyncio.sleep(0.015)
            if chan.recv_ready():
                out = chan.recv(8192)
                if not out:
                    break
                await websocket.send_text(out.decode(errors="ignore"))
            elif chan.exit_status_ready():
                break

    sender = asyncio.create_task(ssh_to_ws())
    receiver = asyncio.create_task(ws_to_ssh())
    try:
        _, pending = await asyncio.wait(
            {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        chan.close()
        client.close()
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
