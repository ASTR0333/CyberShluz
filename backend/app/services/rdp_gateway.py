"""Short-lived TCP bridges from guacd to W-DC through the stand's L-MS.

The Docker host has no route into each isolated OpenStack subnet.  The backend
does, however, have the per-stand unprivileged SSH key for L-MS.  Each browser
RDP launch therefore creates one temporary listener on the backend container;
guacd connects to that listener and the bytes are forwarded through a Paramiko
``direct-tcpip`` channel to W-DC:3389.
"""
from __future__ import annotations

import io
import logging
import select
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

import paramiko

from app.core.config import settings

logger = logging.getLogger(__name__)


class RDPGatewayError(RuntimeError):
    """The browser RDP bridge could not be prepared."""


def _load_private_key(private_key: str):
    for key_class in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return key_class.from_private_key(io.StringIO(private_key))
        except Exception:
            continue
    raise RDPGatewayError("Ключ доступа к L-MS имеет неподдерживаемый формат")


def _wait_for_rdp(transport: paramiko.Transport, target_host: str) -> None:
    """Wait briefly for Windows RDP after Nova reports the VM as ACTIVE."""
    ready_timeout = max(1, int(settings.RDP_READY_TIMEOUT_SECONDS))
    attempt_timeout = max(1, int(settings.RDP_CHANNEL_ATTEMPT_TIMEOUT_SECONDS))
    deadline = time.monotonic() + ready_timeout
    last_error: Exception | None = None

    while True:
        if not transport.is_active():
            raise RDPGatewayError("SSH-соединение с L-MS завершилось во время ожидания W-DC")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            probe = transport.open_channel(
                "direct-tcpip",
                (target_host, 3389),
                ("127.0.0.1", 0),
                timeout=min(float(attempt_timeout), remaining),
            )
            probe.close()
            return
        except paramiko.ChannelException as exc:
            # SSH_OPEN_ADMINISTRATIVELY_PROHIBITED is a configuration error on
            # L-MS and cannot become healthy by waiting for Windows to boot.
            if exc.code == 1:
                raise RDPGatewayError(
                    "SSH-сервер L-MS запрещает TCP-перенаправление (AllowTcpForwarding)"
                ) from exc
            last_error = exc
        except (OSError, paramiko.SSHException) as exc:
            # A filtered/not-yet-open Windows port is commonly surfaced by
            # Paramiko as the generic "Timeout opening channel" exception.
            last_error = exc

        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(2.0, remaining))

    detail = f": {last_error}" if last_error else ""
    raise RDPGatewayError(
        f"W-DC не отвечает на порту RDP 3389 через L-MS "
        f"в течение {ready_timeout} с{detail}"
    )


@dataclass
class RDPTunnel:
    ssh_client: paramiko.SSHClient
    listener: socket.socket
    target_host: str
    target_port: int
    wait_seconds: int
    on_finished: Callable[[str], None]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    _closed: threading.Event = field(default_factory=threading.Event, init=False)
    _client_socket: socket.socket | None = field(default=None, init=False)
    _channel: paramiko.Channel | None = field(default=None, init=False)

    @property
    def port(self) -> int:
        return int(self.listener.getsockname()[1])

    def start(self) -> None:
        threading.Thread(target=self._run, name=f"rdp-tunnel-{self.id[:8]}", daemon=True).start()

    def _run(self) -> None:
        try:
            self.listener.settimeout(self.wait_seconds)
            client_socket, source = self.listener.accept()
            self._client_socket = client_socket
            self.listener.close()

            transport = self.ssh_client.get_transport()
            if not transport or not transport.is_active():
                raise RDPGatewayError("SSH-соединение с L-MS завершилось до запуска RDP")

            channel = transport.open_channel(
                "direct-tcpip",
                (self.target_host, self.target_port),
                (str(source[0]), int(source[1])),
                timeout=12,
            )
            self._channel = channel
            client_socket.setblocking(True)

            while not self._closed.is_set():
                readable, _, _ = select.select([client_socket, channel], [], [], 5)
                if client_socket in readable:
                    data = client_socket.recv(65536)
                    if not data:
                        break
                    channel.sendall(data)
                if channel in readable:
                    data = channel.recv(65536)
                    if not data:
                        break
                    client_socket.sendall(data)
        except (OSError, paramiko.SSHException, RDPGatewayError) as exc:
            if not self._closed.is_set():
                logger.warning("[RDP] Туннель %s завершён: %s", self.id, exc)
        finally:
            self.close()
            self.on_finished(self.id)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        for resource in (self._channel, self._client_socket, self.listener):
            if resource is not None:
                try:
                    resource.close()
                except Exception as exc:
                    logger.debug("[RDP] Ошибка закрытия ресурса туннеля %s: %s", self.id, exc)
        try:
            self.ssh_client.close()
        except Exception as exc:
            logger.debug("[RDP] Ошибка закрытия SSH туннеля %s: %s", self.id, exc)


class RDPTunnelBroker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tunnels: dict[str, RDPTunnel] = {}

    def open(self, lms_ip: str, private_key: str, wdc_ip: str) -> RDPTunnel:
        with self._lock:
            if len(self._tunnels) >= max(1, settings.RDP_MAX_SESSIONS):
                raise RDPGatewayError("Достигнут лимит одновременных веб-сессий W-DC")

        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        listener = None
        try:
            ssh_client.connect(
                hostname=lms_ip,
                username=settings.VM_STUDENT_USER,
                pkey=_load_private_key(private_key),
                timeout=12,
                banner_timeout=15,
                auth_timeout=15,
                look_for_keys=False,
                allow_agent=False,
            )
            transport = ssh_client.get_transport()
            if not transport:
                raise RDPGatewayError("Не удалось создать SSH-транспорт через L-MS")
            transport.set_keepalive(30)

            # Fail while the student is still on the CyberShluz page instead
            # of opening a Guacamole tab which can only show a generic error.
            # Windows may still be booting after Nova reports it as ACTIVE, so
            # readiness is retried within a bounded interval.
            _wait_for_rdp(transport, wdc_ip)

            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # guacd is a separate container on the same private Compose network,
            # so loopback cannot be used here. No host port is published.
            listener.bind(("0.0.0.0", 0))  # nosec B104
            listener.listen(1)
        except Exception as exc:
            if listener is not None:
                listener.close()
            ssh_client.close()
            if isinstance(exc, RDPGatewayError):
                raise
            raise RDPGatewayError(f"W-DC не отвечает по RDP через L-MS: {exc}") from exc

        assert listener is not None
        tunnel = RDPTunnel(
            ssh_client=ssh_client,
            listener=listener,
            target_host=wdc_ip,
            target_port=3389,
            wait_seconds=max(15, settings.RDP_TUNNEL_WAIT_SECONDS),
            on_finished=self._forget,
        )
        with self._lock:
            # Recheck under the lock in case several requests connected to L-MS
            # concurrently while the broker was just below its limit.
            if len(self._tunnels) >= max(1, settings.RDP_MAX_SESSIONS):
                tunnel.close()
                raise RDPGatewayError("Достигнут лимит одновременных веб-сессий W-DC")
            self._tunnels[tunnel.id] = tunnel
        tunnel.start()
        return tunnel

    def _forget(self, tunnel_id: str) -> None:
        with self._lock:
            self._tunnels.pop(tunnel_id, None)

    def close_all(self) -> None:
        with self._lock:
            tunnels = list(self._tunnels.values())
            self._tunnels.clear()
        for tunnel in tunnels:
            tunnel.close()


rdp_tunnel_broker = RDPTunnelBroker()
