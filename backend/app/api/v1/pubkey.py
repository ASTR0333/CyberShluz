import io
import shlex
import socket
import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.models import Stand, StandStatusEnum
from app.core.security import assert_stand_owner_or_teacher, require_student, require_teacher
from app.schemas.contracts import PubkeyRequest

router = APIRouter()


@router.get(
    "/stand/{stand_id}/privkey",
    response_class=PlainTextResponse,
    summary="Системный приватный ключ стенда (для администратора)",
    description=(
        "Возвращает административный приватный ключ, созданный оркестратором и "
        "загруженный в КИ через OpenStack API. Используется только преподавателем "
        "для подключения через ssh labadmin@<floating_ip>."
    ),
)
def get_privkey(stand_id: str, db: Session = Depends(get_db), _=Depends(require_teacher)):
    stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")
    if not stand.private_key:
        raise HTTPException(status_code=404, detail="Приватный ключ ещё не сгенерирован")
    return PlainTextResponse(
        stand.private_key,
        headers={
            "Content-Disposition": f'attachment; filename="stand{stand_id}-admin.pem"',
            "Content-Type": "application/x-pem-file",
        },
    )


@router.post(
    "/stand/{stand_id}/pubkey",
    summary="Добавить SSH-ключ студента на стенд",
    description="Принимает публичный ключ студента и добавляет его в authorized_keys на L-MS.",
)
def add_pubkey(stand_id: str, body: PubkeyRequest, db: Session = Depends(get_db), user=Depends(require_student)):
    stand = db.query(Stand).filter(Stand.id == int(stand_id)).first()
    if not stand:
        raise HTTPException(status_code=404, detail="Стенд не найден")
    assert_stand_owner_or_teacher(user, stand.user_id)
    if stand.status != StandStatusEnum.READY:
        raise HTTPException(status_code=400, detail="Стенд не готов")
    if not stand.ip_address:
        raise HTTPException(status_code=400, detail="IP-адрес стенда не известен")
    if not stand.private_key:
        raise HTTPException(status_code=500, detail="Приватный ключ стенда отсутствует — обратитесь к преподавателю")

    pub = body.public_key.strip()
    if not pub.startswith(("ssh-", "ecdsa-", "sk-")):
        raise HTTPException(status_code=422, detail="Некорректный формат публичного ключа")

    _push_pubkey(stand.ip_address, stand.private_key, pub)
    return {"message": "Ключ успешно добавлен. Подключайтесь: ssh student@" + stand.ip_address}


def _load_pkey(private_key_str: str):
    """Пробует загрузить приватный ключ, перебирая поддерживаемые типы."""
    import paramiko
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey):
        try:
            return cls.from_private_key(io.StringIO(private_key_str))
        except Exception:
            continue
    raise ValueError("Не удалось распознать формат приватного ключа")


def _connect_with_key(ip: str, user: str, pkey, max_wait: int):
    """Пробует подключиться по ключу с ретраями. Auth-фейл — сразу пробрасывает
    исключение, остальные сетевые ошибки — ретраит до max_wait."""
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())   

    deadline = time.time() + max_wait
    last_err: Exception = RuntimeError("timeout")
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            client.connect(
                hostname=ip, username=user, pkey=pkey,
                timeout=8, look_for_keys=False, allow_agent=False,
            )
            print(f"[pubkey] key-auth OK с попытки #{attempt}", flush=True)
            return client
        except paramiko.AuthenticationException:
            client.close()
            raise
        except (paramiko.SSHException, socket.error, EOFError, TimeoutError) as e:
            last_err = e
            print(f"[pubkey] key попытка #{attempt} провалена: {type(e).__name__}: {e}", flush=True)
            time.sleep(3)
    client.close()
    raise last_err


def _push_pubkey(ip: str, system_private_key: str, student_public_key: str, max_wait: int = 30):
    user = settings.VM_ADMIN_USER

    print(f"[pubkey] === Подключение к {user}@{ip} ===", flush=True)
    print(f"[pubkey] Длина приватного ключа: {len(system_private_key)} байт", flush=True)

    try:
        pkey = _load_pkey(system_private_key)
        print(f"[pubkey] Ключ распознан: {type(pkey).__name__}, отпечаток: {pkey.get_fingerprint().hex()}", flush=True)
    except Exception as e:
        print(f"[pubkey] Ошибка разбора приватного ключа: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Не удалось разобрать приватный ключ стенда: {e}")

     
    try:
        client = _connect_with_key(ip, user, pkey, max_wait)
    except Exception as net_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Не удалось подключиться к стенду: {type(net_err).__name__}: {net_err}",
        )

    script = f"""set -eu
student_home=$(getent passwd student | cut -d: -f6)
test -n "$student_home"
install -d -m 0700 -o student -g student "$student_home/.ssh"
printf '%s\\n' {shlex.quote(student_public_key)} >> "$student_home/.ssh/authorized_keys"
sort -u "$student_home/.ssh/authorized_keys" -o "$student_home/.ssh/authorized_keys"
chown student:student "$student_home/.ssh/authorized_keys"
chmod 0600 "$student_home/.ssh/authorized_keys"
"""
    cmd = "sudo -n sh -c " + shlex.quote(script)
    try:
         
         
         
        stdin, stdout, stderr = client.exec_command(cmd, timeout=20)   
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            err = stderr.read().decode(errors="ignore")[:300]
            raise HTTPException(status_code=500, detail=f"Ошибка добавления ключа: {err}")
    finally:
        client.close()
