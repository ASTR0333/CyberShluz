"""
Движок безагентных проверок конфигураций ВМ через SSH (Этап 3).

Архитектура:
    CheckerService — обёртка над ansible-playbook.
    Принимает: список IP, путь к приватному ключу, шаблон лабораторки.
    Возвращает: структурированный CheckResult со списком прошедших и упавших проверок.

Расширяемость:
    Чтобы добавить новую лабу, положите ansible/lab<NN>_<name>.yml.
    Playbook должен возвращать читаемый task name (используется как метка
    в логе) — больше ничего не требуется. Парсер сам соберёт результаты.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    stand_id: str
    status: str   
    log: str
    details: dict[str, bool] = field(default_factory=dict)


class CheckerService:
    """Безагентные SSH-проверки через Ansible."""

    def __init__(self, timeout: int = 120):
        self.timeout = timeout
         
         
        for candidate in (
            Path("/app/ansible"),
            Path(__file__).resolve().parents[3] / "ansible",
            Path(__file__).resolve().parents[2] / "ansible",
        ):
            if candidate.exists():
                self.ANSIBLE_DIR = candidate
                break
        else:
            self.ANSIBLE_DIR = Path("/app/ansible")

    async def check_stand(
        self,
        stand_id: str,
        stand_hosts: dict[str, dict[str, str]],
        ssh_user: str,
        ssh_key_path: str,
        lab_template: str,
    ) -> CheckResult:
        playbook = self.ANSIBLE_DIR / f"{lab_template}.yml"
        if not playbook.exists():
            return CheckResult(
                stand_id=stand_id,
                status="ERROR",
                log=f"Плейбук тестирования не найден: {lab_template}.yml",
            )

        inventory_path = self._write_inventory(stand_hosts, ssh_user, ssh_key_path)

        env = os.environ.copy()
        env["ANSIBLE_STDOUT_CALLBACK"] = "json"
        env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
        env["ANSIBLE_LOAD_CALLBACK_PLUGINS"] = "True"

        cmd = [
            "ansible-playbook",
            str(playbook),
            "-i",
            inventory_path,
            "--private-key",
            ssh_key_path,
            "-u",
            ssh_user,
            "-e",
            f"stand_id={stand_id}",
            "--timeout",
            str(self.timeout),
        ]

        try:
            logger.info("[CHECKER] Stand=%s hosts=%s playbook=%s", stand_id, sorted(stand_hosts), playbook.name)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout + 10,
            )

            parsed = self._parse_ansible_json(
                stdout_b.decode(errors="ignore"),
                stderr_b.decode(errors="ignore"),
                proc.returncode or 0,
            )
            return CheckResult(
                stand_id=stand_id,
                status=parsed["status"],
                log=parsed["log"],
                details=parsed["details"],
            )

        except asyncio.TimeoutError:
            logger.error("[CHECKER] Timeout for stand %s", stand_id)
            return CheckResult(
                stand_id=stand_id,
                status="ERROR",
                log=f"Превышено время ожидания ответа от стенда ({self.timeout} с).",
                details={"ssh_accessible": False},
            )
        except FileNotFoundError as e:
            logger.exception("[CHECKER] ansible-playbook не найден: %s", e)
            return CheckResult(
                stand_id=stand_id,
                status="ERROR",
                log=(
                    "В контейнере не установлен ansible-playbook. "
                    "Проверь, что backend-образ собран свежим Dockerfile."
                ),
            )
        except Exception as e:
            logger.exception("[CHECKER] Failed for stand %s", stand_id)
            return CheckResult(
                stand_id=stand_id,
                status="ERROR",
                log=f"Критическая ошибка движка проверок: {e}",
            )
        finally:
            try:
                os.unlink(inventory_path)
            except OSError:
                pass

    @staticmethod
    def _write_inventory(
        stand_hosts: dict[str, dict[str, str]],
        ssh_user: str,
        ssh_key_path: str,
    ) -> str:
        """Build a role-aware inventory, using direct public addresses when available."""
        groups: dict[str, dict] = {}
        role_groups = {"L-MS": "lms", "L-NFS": "nfs", "L-PGSQL": "pgsql", "W-DC": "wdc"}
        for role, group_name in role_groups.items():
            host = stand_hosts.get(role)
            if not host or not host.get("address"):
                continue
            host_vars: dict[str, str] = {
                "ansible_host": host["address"],
                "ansible_user": ssh_user,
                "expected_hostname": role.lower() + ".cyberprotect.test",
            }
            proxy_jump = host.get("proxy_jump")
            if role == "W-DC":
                host_vars.update(
                    {
                        "ansible_connection": "ssh",
                        "ansible_shell_type": "powershell",
                    }
                )
            if proxy_jump:
                host_vars.update(
                    {
                        "ansible_ssh_common_args": (
                            f"-o ProxyJump={ssh_user}@{proxy_jump} "
                            f"-o IdentityFile={ssh_key_path} "
                            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
                        ),
                    }
                )
            groups[group_name] = {
                "hosts": {role.lower(): host_vars},
            }

        inventory = {"all": {"children": groups}}
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix="lab-inventory-",
            delete=False,
        )
        try:
            json.dump(inventory, handle, ensure_ascii=False)
            handle.flush()
            os.chmod(handle.name, 0o600)
            return handle.name
        finally:
            handle.close()

    def _parse_ansible_json(self, stdout: str, stderr: str, returncode: int) -> dict:
        """Разбираем JSON-вывод Ansible в читаемый отчёт + флаги для UI."""
        details: dict[str, bool] = {"ssh_accessible": True}
        log_lines: list[str] = []
        passed = 0
        failed = 0

        def record_detail(key: str, value: bool) -> None:
            # Some checks (notably hostname) run for several hosts under one
            # task name. One successful host must not hide another host's
            # failure in the aggregate result shown in the UI.
            details[key] = details.get(key, True) and value

        try:
            json_start = stdout.find("{")
            if json_start == -1:
                raise ValueError("Ansible не вернул JSON-структуру")

            data = json.loads(stdout[json_start:])

            for play in data.get("plays", []):
                play_name = play.get("play", {}).get("name", "Playbook")
                log_lines.append(f"▶ {play_name}")
                for task in play.get("tasks", []):
                    task_name = task.get("task", {}).get("name", "(noname)")
                    for host, host_result in task.get("hosts", {}).items():
                        unreachable = bool(host_result.get("unreachable"))
                        is_failed = bool(host_result.get("failed")) or unreachable
                        is_skipped = bool(host_result.get("skipped"))

                        if is_skipped:
                            continue
                        if unreachable:
                            details["ssh_accessible"] = False

                        if is_failed:
                            failed += 1
                            icon = "✗"
                            msg = host_result.get("msg") or host_result.get("stderr") or host_result.get("stdout") or ""
                            tail = f" — {msg}" if msg else ""
                            log_lines.append(f"  {icon} [{host}] {task_name}{tail}")
                        else:
                            passed += 1
                            log_lines.append(f"  ✓ [{host}] {task_name}")

                         
                         
                        tn = task_name.lower()
                        if "9877" in tn:
                            record_detail("port_9877_open", not is_failed)
                        if "snapapi" in tn:
                            record_detail("snapapi_loaded", not is_failed)
                        if "служб" in tn and ("acronis" in tn or "cyber protect" in tn):
                            record_detail("acronis_active", not is_failed)
                        if "firewall" in tn:
                            record_detail("firewall_ok", not is_failed)
                        if "hostname" in tn or "имя хоста" in tn:
                            record_detail("hostname_ok", not is_failed)
                        if "/backupl" in tn:
                            record_detail("storage_directory_ok", not is_failed)
                        if "windows-служб" in tn:
                            record_detail("windows_services_active", not is_failed)
                        if "c:\\backups" in tn:
                            record_detail("windows_storage_directory_ok", not is_failed)

            status = "PASSED" if returncode == 0 and failed == 0 else "FAILED"
            log_lines.append("")
            log_lines.append(f"Итого: ✓ {passed} | ✗ {failed} | rc={returncode}")

        except Exception:
            status = "FAILED"
            log_lines.append("Не удалось разобрать отчёт ansible. Сырой stderr:")
            log_lines.append(stderr[:1000] if stderr else stdout[:1000] or "(пусто)")
            details["ssh_accessible"] = False

        return {
            "status": status,
            "log": "\n".join(log_lines),
            "details": details,
        }

    @classmethod
    def from_env(cls) -> "CheckerService":
        timeout = int(os.getenv("CHECKER_TIMEOUT", "120"))
        return cls(timeout=timeout)
